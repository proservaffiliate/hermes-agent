---
name: nas-mycloud
description: "Verify and configure WD MyCloud NAS drives and web access."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [NAS, MyCloud, WD, storage, network-drive, SMB, remote-access]
    category: productivity
    related_skills: [telephony]
---

# NAS MyCloud Access Setup

This skill lets Hermes autonomously verify drive mappings, test read/write access,
and configure WD MyCloud web interface permissions for network-attached storage.

It does **not** replace a full NAS administration workflow — it covers the
practical setup steps users need to get drives accessible and confirm they work.

## When to Use

- "Check if my NAS drives are accessible"
- "Verify read/write access to U:, W:, X:, Y:, Z:"
- "Set up MyCloud web interface access"
- "Configure NAS share permissions for my account"
- "Enable remote access on MyCloud"
- "Map a network drive to my NAS"
- "MyCloud web portal only shows some of my folders / missing folders"
- "Enable Cloud Access on all shares so they appear on os5.mycloud.com"

## Prerequisites

**Windows (mapped drives):**
- NAS must be reachable on the local network (ping its IP to confirm)
- Drives U:, W:, X:, Y:, Z: must be mapped or you need the NAS IP + share names

**MyCloud web interface:**
- A WD MyCloud or MyCloud OS 5 account at `https://os5.mycloud.com/`
- The NAS device registered to that account

**Script dependencies (optional — for the helper script):**
- Python 3.8+ (stdlib only; no extra packages required)

## How to Run

Ask Hermes directly:

```
"Verify access to my NAS drives and check read/write permissions"
"Set up MyCloud web interface access for my account"
"Map network drives U through Z to my NAS at 192.168.1.100"
```

Or run the helper script directly:

```bash
# Check drive access (Windows)
python scripts/nas_mycloud.py check-drives --drives U W X Y Z

# Test read/write on a specific drive
python scripts/nas_mycloud.py test-rw --path U:\

# Fix specific broken drives in one step (Windows only)
python scripts/nas_mycloud.py fix-drives --drives U Y Z \
    --host 192.168.1.100 \
    --shares U=backup Y=media Z=docs

# Map a single network drive (Windows only, requires admin)
python scripts/nas_mycloud.py map-drive --letter U --unc "\\192.168.1.100\share_name"

# List all shares on the NAS + which drive letters are mapped to each
python scripts/nas_mycloud.py list-shares --host 192.168.1.100

# Ping NAS and probe SMB port (cross-platform)
python scripts/nas_mycloud.py discover --host 192.168.1.100
```

## Quick Reference

| Task | Command / Action |
|------|-----------------|
| Check drives exist | `nas_mycloud.py check-drives --drives U W X Y Z` |
| Test read/write | `nas_mycloud.py test-rw --path <drive_letter>:\` |
| Fix specific broken drives | `nas_mycloud.py fix-drives --drives U Y Z --host <IP> --shares U=share1 Y=share2 Z=share3` |
| List all NAS shares + drive mapping | `nas_mycloud.py list-shares --host <NAS_IP>` |
| Map a single drive | `nas_mycloud.py map-drive --letter <L> --unc <\\IP\share>` |
| Discover NAS shares | `nas_mycloud.py discover --host <NAS_IP>` |
| Web portal | `https://os5.mycloud.com/` |

## Procedure

### Step 1 — Confirm the NAS is reachable

Use `terminal` to ping the NAS IP before anything else:

```bash
ping -n 2 192.168.8.100       # Windows
ping -c 2 192.168.8.100       # Linux / macOS
```

If ping fails, the NAS is offline or the IP is wrong. Check the NAS admin
panel or router DHCP table for the correct IP.

### Step 2 — Verify drive mappings

Run the helper script to report which of the target drives are present,
what UNC path they resolve to, and whether they are reachable:

```bash
python scripts/nas_mycloud.py check-drives --drives U W X Y Z
```

For each drive the script reports:
- `OK` — drive letter exists and root is readable
- `MISSING` — drive letter is not mapped on this machine
- `UNREACHABLE` — drive letter exists but cannot be listed (network error, auth)

### Step 3 — Test read/write access

For each drive that reported `OK`:

```bash
python scripts/nas_mycloud.py test-rw --path U:\
```

The script creates a small probe file, reads it back, and deletes it. Output:
- `READ+WRITE OK` — full access confirmed
- `READ-ONLY` — can list but not write (permission issue)
- `ACCESS DENIED` — drive is mapped but credentials are rejected

### Step 4 — Fix missing or unreachable drives

Use `fix-drives` to repair one or more drives in a single command. It
disconnects any stale mapping, remaps from the NAS, and runs a read/write
check — all automatically:

```bash
# Fix drives U:, Y:, Z: in one pass
python scripts/nas_mycloud.py fix-drives \
    --drives U Y Z \
    --host 192.168.8.100 \
    --shares U=backup Y=media Z=docs
```

Add `--user <username> --password <password>` if the NAS requires credentials.

Each drive in the JSON output shows:
- `status_before` — what was wrong before the fix
- `fixed: true` — whether a remap was attempted
- `rw_check` — `READ+WRITE OK` if the drive is now healthy

For a single drive, `map-drive` can also be used directly:

```bash
python scripts/nas_mycloud.py map-drive --letter X --unc "\\192.168.8.100\media"
```

If `fix-drives` fails with `mapping failed`, verify the share name with
`discover --host <IP>` first, then retry with the correct share name.

### Step 5 — MyCloud web interface — show all folders

The portal at `https://os5.mycloud.com/` only displays shares that have
**Cloud Access enabled**. If you see fewer folders than expected, shares are
either private or Cloud Access is off for them.

**To enable Cloud Access on all shares and make every folder visible:**

1. Sign in to `https://os5.mycloud.com/`
2. Go to **Settings → Shares** (or **Storage → Shares** on older firmware)
3. For each share listed:
   - Click the share name to open its settings
   - Toggle **Cloud Access** → **On**
   - Set your user account's access level to **Read/Write** if not already
   - Click **Save / Apply**
4. Refresh the file browser — every share with Cloud Access on should now
   appear as a top-level folder

**If a share still does not appear after enabling Cloud Access:**
- Confirm the share is **not empty** (empty shares are hidden in the browser)
- Check **Settings → Users** and confirm your account has explicit access to
  that share (not just Public access)

To add another user to a share:
**Settings → Users → Invite** → set the share permission level to **Read/Write**

The helper script can open the portal URL on desktop systems:

```bash
python scripts/nas_mycloud.py open-portal
```

### Step 6 — Enable remote access (optional)

In the MyCloud web interface:
1. Go to **Settings → Remote Access**
2. Enable **Cloud Access**
3. Note the generated access URL — test it from a different network
   (e.g. mobile data) to confirm it works

## Pitfalls

- **Wrong IP after DHCP reassignment.** Assign a static IP to the NAS in
  your router's DHCP reservation table so the drive mappings survive reboots.
- **Credential caching on Windows.** Windows caches SMB credentials per
  server. If you changed the NAS password, open Credential Manager
  (Control Panel) and remove the old entry before re-mapping.
- **Read-only after firmware update.** WD MyCloud OS 5 sometimes resets
  share permissions after a firmware upgrade. Re-check permissions in
  the web portal after any firmware update.
- **`UNREACHABLE` on a correctly mapped drive.** Antivirus or Windows
  Defender Firewall may block SMB traffic. Ensure port 445 is open on
  the local network.
- **Remote access URL unavailable.** Cloud Access requires the NAS to
  reach WD's relay servers. If it fails, check the NAS network settings
  and confirm outbound HTTPS (port 443) is not blocked by your router.
- **Fewer folders than expected on os5.mycloud.com.** Each share must have
  Cloud Access turned ON individually in Settings → Shares. Shares with
  Cloud Access off are invisible to the web portal even if locally mapped.
  Empty shares are also hidden — add at least one file to confirm visibility.

## Verification

After completing the procedure, run:

```bash
python scripts/nas_mycloud.py check-drives --drives U W X Y Z
python scripts/nas_mycloud.py test-rw --path U:\
python scripts/nas_mycloud.py test-rw --path W:\
python scripts/nas_mycloud.py test-rw --path X:\
python scripts/nas_mycloud.py test-rw --path Y:\
python scripts/nas_mycloud.py test-rw --path Z:\
```

All drives should report `OK` from `check-drives` and `READ+WRITE OK` from
`test-rw`. If any drive still fails, revisit Steps 3–4 for that drive.
