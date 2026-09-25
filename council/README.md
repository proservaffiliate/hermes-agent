# Daily Niche Research — Hermes config

One job, one purpose: keep the content operation fresh without you doing the
searching. It runs unattended on weekday mornings, appends dated and cited
findings to an idea bank file, and messages you a short summary.

This is deliberately **the smallest useful thing**. It is not the Council. Get
this running for three clean days before building anything else on Hermes.

---

## What's here

| File | Goes to | Purpose |
|---|---|---|
| `skills/niche-research/SKILL.md` | `~/.hermes/skills/niche-research/` | How the research is done, and the rules it cannot break |
| `install.sh` | run in place | Copies the skill, creates the idea bank, registers the cron job |

The idea bank lands at `~/hermes-council/idea-bank.md`.

---

## Install

```bash
# 1. Point Hermes at your Gemini AI Studio key (free tier may cover this)
export GEMINI_API_KEY=...        # or set it via: hermes setup
hermes model                     # pick a Gemini model

# 2. Install the job
bash install.sh

# 3. Confirm and test
hermes cron list
hermes cron run <job_id>         # fires on the next tick
cat ~/hermes-council/idea-bank.md
```

Edit `SCHEDULE` and `DELIVER` at the top of `install.sh` before running if you
want different timing or delivery to Telegram.

---

## The only test that matters

Run it manually once and read the output. **You are checking one thing: does
every finding carry a real URL and a real date?**

- **Yes** → grounding works. You're done, and it costs you nothing further.
- **No — findings with no URLs, or vague "recent developments"** → the model
  is answering from training data, not the live web. That is worthless for
  this job and actively dangerous for an AI-tools channel. Fix it by switching
  to a web-enabled model. **This is the moment the $25 of OpenRouter credit
  earns its place** — not before.
- **`SEARCH UNAVAILABLE`** → the skill did its job. No search tool is wired
  up. Same fix.

---

## The three-day gate

Do not build the Council, or anything else on Hermes, until this job has run
**unattended and correctly for three consecutive weekdays.**

If it can't clear that bar, the problem is configuration, and you'll know
exactly where to look. If it clears it, you've proven the scheduler, the model
routing, the skill loading and the delivery path all work — and the Council
becomes a much smaller job, because it reuses all four.

---

## Things worth knowing

- **Your PC must be awake when the job fires.** With Hermes local and no VPS,
  a sleeping machine means no run. Either leave it on, or set `SCHEDULE` to a
  time you're reliably at the desk.
- **Cron runs skip agent memory** (`skip_memory=True` is the Hermes default).
  That's why findings go to a file. The idea bank is the durable record, not
  the agent's memory.
- **Runs time out after 600 seconds of inactivity**, not total runtime — the
  timer resets on every tool and API call. A long multi-search run is fine.
  Override with `HERMES_CRON_TIMEOUT` if you ever need to.
  (Note: the bundled `hermes-agent` skill doc says "3-minute hard interrupt."
  That disagrees with `cron/scheduler.py`, which is what actually runs. The
  code is right.)
- **Nothing here publishes anything.** The skill only reads and appends. It
  cannot post, and it cannot mark a claim verified — that stays manual, and
  it's the gate between research and publishing.

---

## Changing niche

Edit the `Configuration` block at the top of `SKILL.md` — `niche` and
`audience`. Nothing else needs to change. Re-run `install.sh` to copy the
updated skill across.
