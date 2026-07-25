#!/usr/bin/env python3
"""
NAS / WD MyCloud access verification and setup helper.

Usage:
    python nas_mycloud.py check-drives --drives U W X Y Z
    python nas_mycloud.py test-rw --path U:\
    python nas_mycloud.py map-drive --letter X --unc "\\192.168.1.100\share"
    python nas_mycloud.py fix-drives --drives U Y Z --host 192.168.1.100 --shares U=share1 Y=share2 Z=share3
    python nas_mycloud.py discover --host 192.168.1.100
    python nas_mycloud.py open-portal
"""

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


MYCLOUD_PORTAL = "https://os5.mycloud.com/"
SMB_PORT = 445


def _is_windows() -> bool:
    return platform.system() == "Windows"


# ---------------------------------------------------------------------------
# check-drives
# ---------------------------------------------------------------------------

def check_drives(drives: list[str]) -> dict:
    results = {}
    for letter in drives:
        drive = letter.rstrip(":\\/ ")
        if _is_windows():
            root = Path(f"{drive}:\\")
        else:
            # On non-Windows, treat as a path prefix for testing purposes
            root = Path(f"/mnt/{drive.lower()}")

        if not root.exists():
            results[drive] = {"status": "MISSING", "path": str(root)}
            continue

        try:
            list(root.iterdir())
            results[drive] = {"status": "OK", "path": str(root)}
        except PermissionError:
            results[drive] = {"status": "UNREACHABLE", "path": str(root), "reason": "permission denied"}
        except OSError as exc:
            results[drive] = {"status": "UNREACHABLE", "path": str(root), "reason": str(exc)}

    return results


# ---------------------------------------------------------------------------
# test-rw
# ---------------------------------------------------------------------------

def test_rw(path: str) -> dict:
    root = Path(path)
    if not root.exists():
        return {"status": "MISSING", "path": path}

    probe_name = f".hermes_nas_probe_{uuid.uuid4().hex[:8]}.tmp"
    probe = root / probe_name
    payload = "hermes-nas-probe"

    try:
        probe.write_text(payload)
    except (PermissionError, OSError) as exc:
        # Check if at least readable
        try:
            list(root.iterdir())
            return {"status": "READ-ONLY", "path": path, "reason": str(exc)}
        except OSError:
            return {"status": "ACCESS DENIED", "path": path, "reason": str(exc)}

    try:
        content = probe.read_text()
        if content != payload:
            return {"status": "READ-WRITE ERROR", "path": path, "reason": "read-back mismatch"}
    except OSError as exc:
        return {"status": "READ-WRITE ERROR", "path": path, "reason": str(exc)}
    finally:
        try:
            probe.unlink()
        except OSError:
            pass

    return {"status": "READ+WRITE OK", "path": path}


# ---------------------------------------------------------------------------
# map-drive  (Windows only)
# ---------------------------------------------------------------------------

def map_drive(letter: str, unc: str, user: str = None, password: str = None) -> dict:
    if not _is_windows():
        return {"status": "ERROR", "reason": "map-drive is Windows-only; on Linux/macOS use mount.cifs or Finder"}

    letter = letter.rstrip(":\\").upper()
    cmd = ["net", "use", f"{letter}:", unc, "/persistent:yes"]
    if user:
        cmd += [f"/user:{user}"]
    if password:
        cmd += [password]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return {"status": "MAPPED", "drive": f"{letter}:", "unc": unc}
        return {
            "status": "ERROR",
            "drive": f"{letter}:",
            "unc": unc,
            "reason": (result.stderr or result.stdout).strip(),
        }
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "reason": "net use timed out — NAS may be unreachable"}
    except FileNotFoundError:
        return {"status": "ERROR", "reason": "'net' command not found; this must run on Windows"}


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

def discover(host: str) -> dict:
    result: dict = {"host": host}

    # Reachability via TCP to SMB port
    try:
        with socket.create_connection((host, SMB_PORT), timeout=5):
            result["smb_port_open"] = True
    except (OSError, socket.timeout):
        result["smb_port_open"] = False

    # Ping
    ping_flag = "-n" if _is_windows() else "-c"
    try:
        proc = subprocess.run(
            ["ping", ping_flag, "2", host],
            capture_output=True,
            text=True,
            timeout=10,
        )
        result["ping_ok"] = proc.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        result["ping_ok"] = None

    # SMB share enumeration (Windows only via net view)
    if _is_windows():
        try:
            proc = subprocess.run(
                ["net", "view", f"\\\\{host}"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode == 0:
                shares = [
                    line.split()[0]
                    for line in proc.stdout.splitlines()
                    if line and not line.startswith("-") and line[0].isalpha()
                ]
                result["shares"] = shares
            else:
                result["shares_error"] = (proc.stderr or proc.stdout).strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            result["shares_error"] = "net view timed out or not available"

    return result


# ---------------------------------------------------------------------------
# fix-drives  (Windows only)
# ---------------------------------------------------------------------------

def _unmap_drive(letter: str) -> dict:
    """Disconnect a drive letter, ignoring 'not connected' errors."""
    letter = letter.rstrip(":\\").upper()
    try:
        result = subprocess.run(
            ["net", "use", f"{letter}:", "/delete", "/yes"],
            capture_output=True, text=True, timeout=15,
        )
        # returncode 2 = drive was not connected — treat as OK
        if result.returncode in (0, 2):
            return {"unmapped": True}
        return {"unmapped": False, "reason": (result.stderr or result.stdout).strip()}
    except subprocess.TimeoutExpired:
        return {"unmapped": False, "reason": "net use /delete timed out"}
    except FileNotFoundError:
        return {"unmapped": False, "reason": "'net' not found — must run on Windows"}


def fix_drives(
    drives: list[str],
    host: str,
    share_map: dict[str, str],
    user: str = None,
    password: str = None,
) -> dict:
    """
    For each drive letter:
      1. Check current status.
      2. If MISSING or UNREACHABLE: unmap (if stale) then remap.
      3. Verify read/write after remapping.
    """
    if not _is_windows():
        return {
            "status": "ERROR",
            "reason": "fix-drives is Windows-only; on Linux/macOS use mount.cifs",
        }

    results = {}
    for letter in drives:
        drv = letter.rstrip(":\\").upper()
        root = Path(f"{drv}:\\")

        # 1 — current state
        status_before = check_drives([drv])[drv]["status"]

        # 2 — remediate if not healthy
        if status_before != "OK":
            unmap_result = _unmap_drive(drv)

            share = share_map.get(drv) or share_map.get(drv.lower())
            if not share:
                results[drv] = {
                    "status_before": status_before,
                    "fixed": False,
                    "reason": f"no share name provided for {drv}: — pass {drv}=<share> in --shares",
                }
                continue

            unc = f"\\\\{host}\\{share}"
            map_result = map_drive(drv, unc, user=user, password=password)

            if map_result["status"] != "MAPPED":
                results[drv] = {
                    "status_before": status_before,
                    "fixed": False,
                    "unc": unc,
                    "reason": map_result.get("reason", "mapping failed"),
                }
                continue
        else:
            unmap_result = None
            map_result = None

        # 3 — verify read/write
        rw = test_rw(str(root))
        results[drv] = {
            "status_before": status_before,
            "fixed": status_before != "OK",
            "rw_check": rw["status"],
        }
        if map_result:
            results[drv]["unc"] = map_result.get("unc", "")

    return results


# ---------------------------------------------------------------------------
# open-portal
# ---------------------------------------------------------------------------

def open_portal() -> dict:
    import webbrowser
    webbrowser.open(MYCLOUD_PORTAL)
    return {"status": "OPENED", "url": MYCLOUD_PORTAL}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print(data: dict) -> None:
    print(json.dumps(data, indent=2))


def main(argv: list[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description="NAS / WD MyCloud access verification and setup helper."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check-drives", help="Check if drive letters exist and are readable")
    p_check.add_argument("--drives", nargs="+", required=True, metavar="LETTER",
                         help="Drive letters to check (e.g. U W X Y Z)")

    p_rw = sub.add_parser("test-rw", help="Test read/write access on a path")
    p_rw.add_argument("--path", required=True, help="Path to test (e.g. U:\\ or /mnt/nas)")

    p_map = sub.add_parser("map-drive", help="Map a network drive (Windows only)")
    p_map.add_argument("--letter", required=True, help="Drive letter to assign (e.g. X)")
    p_map.add_argument("--unc", required=True, help="UNC path (e.g. \\\\192.168.1.100\\share)")
    p_map.add_argument("--user", help="SMB username (optional)")
    p_map.add_argument("--password", help="SMB password (optional)")

    p_fix = sub.add_parser(
        "fix-drives",
        help="Unmap stale drives, remap from NAS, and verify read/write (Windows only)",
    )
    p_fix.add_argument("--drives", nargs="+", required=True, metavar="LETTER",
                       help="Drive letters to fix (e.g. U Y Z)")
    p_fix.add_argument("--host", required=True, help="NAS IP or hostname")
    p_fix.add_argument(
        "--shares", nargs="+", required=True, metavar="LETTER=SHARE",
        help="Drive-to-share mapping (e.g. U=backup Y=media Z=docs)",
    )
    p_fix.add_argument("--user", help="SMB username (optional)")
    p_fix.add_argument("--password", help="SMB password (optional)")

    p_disc = sub.add_parser("discover", help="Ping NAS and probe SMB port / shares")
    p_disc.add_argument("--host", required=True, help="NAS IP or hostname")

    sub.add_parser("open-portal", help=f"Open {MYCLOUD_PORTAL} in the default browser")

    args = parser.parse_args(argv)

    if args.cmd == "check-drives":
        _print(check_drives(args.drives))
    elif args.cmd == "test-rw":
        _print(test_rw(args.path))
    elif args.cmd == "map-drive":
        _print(map_drive(args.letter, args.unc,
                         user=getattr(args, "user", None),
                         password=getattr(args, "password", None)))
    elif args.cmd == "fix-drives":
        share_map = {}
        for entry in args.shares:
            if "=" not in entry:
                print(f"ERROR: --shares entries must be LETTER=share_name, got: {entry!r}",
                      file=sys.stderr)
                return 1
            k, v = entry.split("=", 1)
            share_map[k.upper()] = v
        _print(fix_drives(
            args.drives, args.host, share_map,
            user=getattr(args, "user", None),
            password=getattr(args, "password", None),
        ))
    elif args.cmd == "discover":
        _print(discover(args.host))
    elif args.cmd == "open-portal":
        _print(open_portal())

    return 0


if __name__ == "__main__":
    sys.exit(main())
