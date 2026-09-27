#!/usr/bin/env bash
# Registers the Council of Thought MCP server with Hermes.
#
# After this, Hermes can convene the council itself — on a cron schedule,
# from Telegram, or in the TUI — instead of the council only being callable
# from Antigravity or Claude Code.
#
# Safe to re-run: it will not create a duplicate registration.
#
# CREDENTIALS ARE NOT PASSED HERE, deliberately. The council server reads
# provider keys from the environment at call time, so whatever the keeper
# puts in Hermes's environment is what the seats use. Putting a key in this
# script would fork the source of truth, which is the one thing the
# credential boundary exists to prevent.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_DIR="$REPO_DIR/council/mcp"
SERVER="$MCP_DIR/council_mcp.py"
NAME="council"

# --- edit if you want records somewhere else -----------------------------
COUNCIL_HOME="${COUNCIL_HOME:-$HOME/council}"
# -------------------------------------------------------------------------

say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

say "==> Checking prerequisites"
command -v hermes >/dev/null 2>&1 || die "hermes not on PATH. Install Hermes first."
[ -f "$SERVER" ] || die "Council server not found at $SERVER"

PY="$(command -v python3 || true)"
[ -n "$PY" ] || die "python3 not on PATH."
say "    hermes:  $(command -v hermes)"
say "    python3: $PY"
say "    server:  $SERVER"

say "==> Installing the server's one dependency (mcp>=2)"
"$PY" -m pip install --quiet --upgrade -r "$MCP_DIR/requirements.txt" \
  || die "pip install failed. Install '$MCP_DIR/requirements.txt' into $PY yourself, then re-run."

say "==> Verifying the server imports before registering it"
( cd "$MCP_DIR" && "$PY" -c "import council_mcp" ) \
  || die "council_mcp.py failed to import under $PY. Fix that before wiring."

say "==> Installing the council-protocol skill"
SKILL_SRC="$REPO_DIR/council/skills/council-protocol"
SKILL_DST="$HERMES_HOME/skills/council-protocol"
mkdir -p "$SKILL_DST"
cp "$SKILL_SRC/SKILL.md" "$SKILL_DST/SKILL.md"
say "    $SKILL_DST/SKILL.md"
say "    (teaches Hermes when to convene and who decides — the tools alone do not)"

say "==> Creating records directory"
mkdir -p "$COUNCIL_HOME"
say "    $COUNCIL_HOME"

if hermes mcp list 2>/dev/null | grep -qw "$NAME"; then
  say "==> '$NAME' is already registered. Leaving it alone."
  say "    To re-register:  hermes mcp remove $NAME  &&  bash $0"
else
  say "==> Registering with Hermes"
  # --args uses argparse.REMAINDER and must be the LAST option on the line.
  # Anything after it is swallowed as command argv.
  hermes mcp add "$NAME" \
    --env "COUNCIL_HOME=$COUNCIL_HOME" "PYTHONPATH=$MCP_DIR" \
    --command "$PY" \
    --args "$SERVER"
  say "    registered as '$NAME'"
fi

say "==> Testing the connection"
if hermes mcp test "$NAME"; then
  say
  say "Done. Hermes can now call the council."
else
  say
  say "Registered, but the connection test failed. Check with:"
  say "    hermes mcp list"
  say "    hermes mcp test $NAME"
fi

cat <<EOF

Next:
  hermes mcp list                     # confirm 'council' is present
  hermes                              # then ask it: "what's the council status?"

Records land in $COUNCIL_HOME.
Seats with no API key in Hermes's environment hand back a prompt to paste
rather than failing, so this works before the keeper is wired.
EOF
