"""Tests for the remote-control plugin.

Covers plugins/remote-control/__init__.py:
  * Token generation and pairing URL format.
  * on_session_start hook starts the server and prints the URL.
  * on_session_end hook stops the server.
  * /remote-control slash command: status / refresh / stop / unknown.
  * WebSocket authentication: valid token accepted, bad token rejected.
  * Authenticated messages are forwarded to inject_fn.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import threading
import time
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

def _load_plugin():
    repo_root = Path(__file__).resolve().parents[2]
    init_path = repo_root / "plugins" / "remote-control" / "__init__.py"
    spec = importlib.util.spec_from_file_location("rc_plugin", init_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fresh_plugin():
    """Return a freshly-imported module so global state is reset."""
    name = "rc_plugin_fresh"
    if name in sys.modules:
        del sys.modules[name]
    return _load_plugin()


def _make_ctx(inject_fn=None):
    ctx = MagicMock()
    ctx.inject_message = inject_fn or MagicMock(return_value=True)
    return ctx


def _collect_registrations(plugin_mod, ctx):
    """Run register() and return the slash-command handler and hooks."""
    hooks = {}
    commands = {}

    def fake_hook(name, fn):
        hooks[name] = fn

    def fake_cmd(name, handler=None, description=None):
        commands[name] = handler

    ctx.register_hook.side_effect = fake_hook
    ctx.register_command.side_effect = fake_cmd
    plugin_mod.register(ctx)
    return hooks, commands


# ---------------------------------------------------------------------------
# Unit tests — pure helpers (no I/O)
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_new_token_is_urlsafe_string(self):
        mod = _load_plugin()
        token = mod._new_token()
        assert isinstance(token, str) and len(token) >= 20

    def test_tokens_are_unique(self):
        mod = _load_plugin()
        tokens = {mod._new_token() for _ in range(10)}
        assert len(tokens) == 10

    def test_pairing_url_contains_port_and_token(self):
        mod = _load_plugin()
        url = mod._pairing_url("tok123", 54321)
        assert "54321" in url
        assert "tok123" in url
        assert url.startswith("https://")

    def test_free_port_is_in_range(self):
        mod = _load_plugin()
        port = mod._free_port()
        assert 1024 < port < 65536


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------

class TestRegistration:
    def test_register_wires_expected_hooks(self):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        hooks, commands = _collect_registrations(mod, ctx)
        assert "on_session_start" in hooks
        assert "on_session_end" in hooks

    def test_register_wires_slash_command(self):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        hooks, commands = _collect_registrations(mod, ctx)
        assert "remote-control" in commands


# ---------------------------------------------------------------------------
# Slash command tests (no server started)
# ---------------------------------------------------------------------------

class TestSlashCommand:
    def _handler(self):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        _, commands = _collect_registrations(mod, ctx)
        return commands["remote-control"], mod

    def test_status_when_not_running(self):
        handler, _ = self._handler()
        result = handler("status")
        assert "not running" in result.lower()

    def test_refresh_when_not_running(self):
        handler, _ = self._handler()
        result = handler("refresh")
        assert "not running" in result.lower()

    def test_stop_when_not_running(self):
        handler, _ = self._handler()
        result = handler("stop")
        assert "not running" in result.lower()

    def test_unknown_subcommand(self):
        handler, _ = self._handler()
        result = handler("bogus_cmd")
        assert "unknown" in result.lower() or "bogus_cmd" in result

    def test_empty_args_returns_status(self):
        handler, _ = self._handler()
        result = handler("")
        assert "not running" in result.lower()

    def test_refresh_rotates_token(self):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        _, commands = _collect_registrations(mod, ctx)
        handler = commands["remote-control"]

        # Manually set up a fake running server state
        mod._port = 12345
        mod._token = "original_token"

        result = handler("refresh")
        assert "original_token" not in result
        assert mod._token != "original_token"

    def test_stop_clears_port(self):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        _, commands = _collect_registrations(mod, ctx)
        handler = commands["remote-control"]

        mod._port = 12345
        mod._token = "some_token"

        handler("stop")
        assert mod._port == 0

    def test_status_when_running_includes_url(self):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        _, commands = _collect_registrations(mod, ctx)
        handler = commands["remote-control"]

        mod._port = 54321
        mod._token = "mytoken"

        result = handler("status")
        assert "54321" in result
        assert "mytoken" in result


# ---------------------------------------------------------------------------
# Integration: session hooks start/stop the server
# ---------------------------------------------------------------------------

class TestServerLifecycle:
    def test_session_start_sets_port_and_token(self, capsys):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        hooks, _ = _collect_registrations(mod, ctx)

        hooks["on_session_start"]()
        try:
            assert mod._port > 0
            assert mod._token != ""
            captured = capsys.readouterr()
            assert "127.0.0.1" in captured.out
            assert "Pairing URL" in captured.out
        finally:
            hooks["on_session_end"]()

    def test_session_end_clears_port(self, capsys):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        hooks, _ = _collect_registrations(mod, ctx)

        hooks["on_session_start"]()
        time.sleep(0.05)
        hooks["on_session_end"]()
        time.sleep(0.05)
        assert mod._port == 0


# ---------------------------------------------------------------------------
# Integration: WebSocket auth and message relay
# ---------------------------------------------------------------------------

class TestWebSocketProtocol:
    """Spin up a real WebSocket server and verify protocol behaviour."""

    def _run_client(self, port: int, token: str, messages: list, results: list):
        import json as _json

        async def _client():
            try:
                import websockets
            except ImportError:
                results.append(("skip", "websockets not installed"))
                return

            uri = f"ws://127.0.0.1:{port}"
            try:
                async with websockets.connect(uri, open_timeout=3) as ws:
                    await ws.send(_json.dumps({"token": token}))
                    resp = await asyncio.wait_for(ws.recv(), timeout=3)
                    results.append(("auth", _json.loads(resp)))
                    for msg in messages:
                        await ws.send(_json.dumps({"content": msg, "role": "user"}))
                    await asyncio.sleep(0.1)
            except Exception as exc:
                results.append(("error", str(exc)))

        asyncio.run(_client())

    def test_valid_token_accepted(self):
        mod = _fresh_plugin()
        injected: List[str] = []

        def mock_inject(content, role="user"):
            injected.append(content)
            return True

        ctx = _make_ctx(inject_fn=mock_inject)
        hooks, _ = _collect_registrations(mod, ctx)
        hooks["on_session_start"]()

        port, token = mod._port, mod._token
        time.sleep(0.1)

        results: list = []
        t = threading.Thread(
            target=self._run_client,
            args=(port, token, ["hello from remote"], results),
        )
        t.start()
        t.join(timeout=5)

        hooks["on_session_end"]()

        if results and results[0] == ("skip", "websockets not installed"):
            import pytest
            pytest.skip("websockets not installed in test environment")

        assert any(r[0] == "auth" for r in results), f"unexpected results: {results}"
        assert "hello from remote" in injected

    def test_bad_token_rejected(self):
        mod = _fresh_plugin()
        ctx = _make_ctx()
        hooks, _ = _collect_registrations(mod, ctx)
        hooks["on_session_start"]()

        port = mod._port
        time.sleep(0.1)

        results: list = []
        t = threading.Thread(
            target=self._run_client,
            args=(port, "WRONG_TOKEN", [], results),
        )
        t.start()
        t.join(timeout=5)

        hooks["on_session_end"]()

        if results and results[0] == ("skip", "websockets not installed"):
            import pytest
            pytest.skip("websockets not installed in test environment")

        # Bad token — should get an error/disconnect, not auth_ok
        auth_oks = [r for r in results if r[0] == "auth" and r[1].get("type") == "auth_ok"]
        assert not auth_oks, f"bad token should not authenticate: {results}"
