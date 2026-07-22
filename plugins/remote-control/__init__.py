"""remote-control plugin — drive a Hermes session from claude.ai or any WebSocket client.

On session start the plugin:
1. Finds a free localhost port.
2. Generates a single-use pairing token.
3. Starts a background WebSocket server bound to 127.0.0.1:<port>.
4. Prints the pairing URL to the console.

A remote client authenticates by sending ``{"token": "<value>"}`` as its
first message.  All subsequent messages are forwarded into the active
Hermes conversation via ``ctx.inject_message()``.

The server is torn down automatically when the session ends.

Usage
-----
Enable via the standard plugin mechanism:

    hermes plugins enable remote-control

Or with the one-liner:

    hermes plugins enable remote-control && hermes

Then open the printed URL in a browser or send it to a WebSocket client
(e.g. wscat, websocat, or the claude.ai remote-control UI).

Slash command
-------------
/remote-control           — show server status and current pairing URL
/remote-control refresh   — rotate the token and print a new pairing URL
/remote-control stop      — shut down the server for this session
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import socket
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level server state (one server per process)
# ---------------------------------------------------------------------------

_loop: Optional[asyncio.AbstractEventLoop] = None
_server = None               # websockets.WebSocketServer
_server_thread: Optional[threading.Thread] = None
_port: int = 0
_token: str = ""
_inject_fn: Optional[Callable[..., bool]] = None
_active: bool = False        # True once a client has authenticated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _new_token() -> str:
    return secrets.token_urlsafe(24)


def _pairing_url(token: str, port: int) -> str:
    # The WS base-URL is embedded so any client (browser, wscat, etc.) can
    # connect directly.  claude.ai's remote-control UI reads this format.
    return f"https://claude.ai/remote?ws=ws%3A%2F%2F127.0.0.1%3A{port}&token={token}"


def _status_text() -> str:
    global _port, _token, _active
    if not _port:
        return "Remote control server is not running."
    url = _pairing_url(_token, _port)
    connected = "client connected" if _active else "waiting for connection"
    return (
        f"Remote control server: ws://127.0.0.1:{_port}  ({connected})\n"
        f"Pairing URL: {url}"
    )


# ---------------------------------------------------------------------------
# WebSocket handler (runs inside the background event loop)
# ---------------------------------------------------------------------------

async def _handle_connection(websocket) -> None:
    global _token, _inject_fn, _active

    # Step 1 — authenticate with the pairing token
    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=15)
    except asyncio.TimeoutError:
        await websocket.close(1008, "authentication timeout")
        return

    try:
        payload = json.loads(raw)
        presented_token = payload.get("token", "")
    except (json.JSONDecodeError, AttributeError):
        presented_token = str(raw).strip()

    if not secrets.compare_digest(presented_token, _token):
        logger.warning("[remote-control] rejected connection: bad token")
        await websocket.close(1008, "invalid token")
        return

    _active = True
    logger.info("[remote-control] client authenticated on port %d", _port)

    try:
        await websocket.send(json.dumps({"type": "auth_ok", "session": "hermes"}))
    except Exception:
        _active = False
        return

    # Step 2 — relay messages into the active Hermes conversation
    try:
        async for raw_msg in websocket:
            try:
                data = json.loads(raw_msg)
                content = data.get("content") or data.get("text") or data.get("message")
                if not content:
                    content = str(raw_msg)
                role = data.get("role", "user")
            except (json.JSONDecodeError, TypeError):
                content = str(raw_msg)
                role = "user"

            if _inject_fn is not None:
                ok = _inject_fn(content, role=role)
                if not ok:
                    logger.warning("[remote-control] inject_message returned False")
            else:
                logger.warning("[remote-control] no inject function available")
    except Exception as exc:
        logger.debug("[remote-control] client disconnected: %s", exc)
    finally:
        _active = False


# ---------------------------------------------------------------------------
# Background thread that owns the asyncio event loop + WebSocket server
# ---------------------------------------------------------------------------

def _run_loop(port: int) -> None:
    global _loop, _server

    try:
        import websockets  # type: ignore[import-untyped]
    except ImportError:
        logger.error(
            "[remote-control] 'websockets' is not installed — "
            "run: pip install 'websockets>=15'"
        )
        return

    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    async def _main() -> None:
        global _server
        async with websockets.serve(_handle_connection, "127.0.0.1", port) as srv:
            _server = srv
            await srv.wait_closed()

    try:
        _loop.run_until_complete(_main())
    except Exception as exc:
        logger.debug("[remote-control] event loop exited: %s", exc)
    finally:
        try:
            _loop.close()
        except Exception:
            pass
        _loop = None
        _server = None


def _start(inject_fn: Callable[..., bool]) -> tuple[int, str]:
    global _server_thread, _port, _token, _inject_fn

    _inject_fn = inject_fn
    _port = _free_port()
    _token = _new_token()

    _server_thread = threading.Thread(
        target=_run_loop,
        args=(_port,),
        name="hermes-remote-control",
        daemon=True,
    )
    _server_thread.start()
    return _port, _token


def _stop() -> None:
    global _loop, _server, _port, _token, _active, _inject_fn
    if _loop is not None and _server is not None:
        _loop.call_soon_threadsafe(_server.close)
    _port = 0
    _token = ""
    _active = False
    _inject_fn = None


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

def register(ctx) -> None:

    def on_session_start(**_kwargs) -> None:
        port, token = _start(ctx.inject_message)
        url = _pairing_url(token, port)
        print(f"\n[remote-control] Server listening on ws://127.0.0.1:{port}")
        print(f"[remote-control] Pairing URL: {url}\n")

    def on_session_end(**_kwargs) -> None:
        _stop()

    def handle_slash(raw_args: str) -> str:
        global _token, _port
        sub = raw_args.strip().split()[0] if raw_args.strip() else "status"

        if sub in ("status", ""):
            return _status_text()

        if sub == "refresh":
            if not _port:
                return "Remote control server is not running."
            _token = _new_token()
            url = _pairing_url(_token, _port)
            return f"Token rotated. New pairing URL:\n{url}"

        if sub == "stop":
            if not _port:
                return "Remote control server is not running."
            _stop()
            return "Remote control server stopped."

        return (
            f"Unknown subcommand: {sub!r}\n\n"
            "Available subcommands:\n"
            "  status   — show server address and pairing URL\n"
            "  refresh  — rotate the token and print a new URL\n"
            "  stop     — shut down the server for this session"
        )

    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("on_session_end", on_session_end)
    ctx.register_command(
        "remote-control",
        handler=handle_slash,
        description=(
            "Show/manage the remote-control WebSocket server "
            "(status | refresh | stop)."
        ),
    )
