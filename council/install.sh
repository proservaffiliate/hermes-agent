#!/usr/bin/env bash
# Installs the daily niche research job into Hermes.
# Safe to re-run: it will not duplicate an existing job with the same name.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SKILL_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills/niche-research"
SKILL_DST="$HERMES_HOME/skills/niche-research"
BANK_DIR="$HOME/hermes-council"

# --- edit these two if you want ------------------------------------------
SCHEDULE="0 9 * * 1-5"     # weekdays 09:00 local. PC must be awake.
DELIVER="local"            # or: telegram, discord, signal, platform:chat_id
# -------------------------------------------------------------------------

echo "==> Installing niche-research skill"
mkdir -p "$SKILL_DST"
cp "$SKILL_SRC/SKILL.md" "$SKILL_DST/SKILL.md"
echo "    $SKILL_DST/SKILL.md"

echo "==> Creating idea bank"
mkdir -p "$BANK_DIR"
if [ ! -f "$BANK_DIR/idea-bank.md" ]; then
  printf '# Idea Bank\n\nAppended daily by the niche-research Hermes skill.\nEvery claim is UNVERIFIED until a human opens the source page.\n' \
    > "$BANK_DIR/idea-bank.md"
  echo "    created $BANK_DIR/idea-bank.md"
else
  echo "    $BANK_DIR/idea-bank.md already exists, left untouched"
fi

echo "==> Checking for an existing job"
if hermes cron list --all 2>/dev/null | grep -qi "Daily Niche Research"; then
  echo "    A job named 'Daily Niche Research' already exists. Not creating a second."
  echo "    Edit it with:  hermes cron list   then   hermes cron edit <id> --schedule '$SCHEDULE'"
  exit 0
fi

echo "==> Creating cron job"
hermes cron create "$SCHEDULE" \
  "Run the niche-research skill for today. Follow its hard rules exactly: every finding needs a live source URL and a date, and if nothing genuinely new is found, report NOTHING NEW TODAY rather than padding the list." \
  --name "Daily Niche Research" \
  --skill niche-research \
  --deliver "$DELIVER" \
  --workdir "$BANK_DIR"

echo
echo "Done. Next:"
echo "  hermes cron list                 # confirm it is scheduled"
echo "  hermes cron run <job_id>         # fire it on the next tick to test"
echo "  cat $BANK_DIR/idea-bank.md       # check it actually wrote something"
