---
name: niche-research
description: Daily grounded research sweep for the content niche. Finds what genuinely changed in the last 7 days, verifies every claim against a live source, and appends dated, cited entries to the idea bank.
version: 1.0.0
author: Founder
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, content, affiliate, daily, grounded]
    category: research
---

# Daily Niche Research

Keeps the content operation fresh and factually current. Runs unattended on a
schedule, writes to the idea bank, and reports only what is genuinely new.

---

## Configuration — edit this block, not the rest of the file

```yaml
niche:        "AI and automation tools for small business owners and solo operators"
audience:     "Non-technical owner-operators running a business with 1-20 people"
platforms:    "TikTok, YouTube Shorts, Instagram Reels"
lookback:     "7 days"
idea_bank:    "~/hermes-council/idea-bank.md"
max_findings: 5
```

To change niche, edit `niche` and `audience` above. Nothing else needs to change.

---

## Hard rules — these override everything else

These exist because a research agent that invents findings is worse than no
research agent. A fabricated tool recommendation becomes a published video,
which becomes a broken affiliate link and a damaged channel.

1. **Every finding needs a live source URL and a date.** No URL, no finding.
2. **Never report anything you did not actually retrieve this run.** Do not
   fill gaps from training data. Do not describe what a tool "probably" costs.
3. **If nothing genuinely new is found, output `NOTHING NEW TODAY` and stop.**
   A short honest report is the correct output. Never pad the list to look
   productive. Some days there is no news.
4. **Never state a price, commission rate, or affiliate term you have not read
   on the vendor's own page this run.** Write `UNVERIFIED` instead.
5. **If a search tool fails or returns nothing, say so explicitly.** Report
   `SEARCH UNAVAILABLE — no findings this run`. Do not substitute recalled
   knowledge for a failed search.
6. **Flag contradictions.** If a finding contradicts something already in the
   idea bank, mark it `⚠ CONTRADICTS PRIOR ENTRY` and name the entry.

---

## Procedure

### 1. Search
Use available web search tools to find developments in `niche` from the last
`lookback`. Cover:
- New tool launches and major feature releases
- Pricing changes, tier changes, free-tier removals
- Shutdowns, acquisitions, deprecations
- Affiliate or partner program changes
- Notably high-performing posts in this niche on `platforms`

Run several distinct searches. One broad query is not a sweep.

### 2. Filter
Keep only items that pass all three:
- **Dated within `lookback`** and confirmed by a retrievable source
- **Relevant to `audience`** — not developer news, not model benchmarks
- **Filmable** — could plausibly become a 60-second video

Discard everything else silently. Quality over count. Fewer than
`max_findings` is normal and fine.

### 3. Write to the idea bank
Append to the file at `idea_bank` (create it with an `# Idea Bank` heading if
absent). Never overwrite or reorder existing content — append only.

Use exactly this entry format:

```markdown
## YYYY-MM-DD

### <Tool or event name>
- **What changed:** <one sentence, plain language>
- **Source:** <full URL>
- **Source date:** YYYY-MM-DD
- **Why the audience cares:** <one sentence, no jargon>
- **Content angle:** <a 60-second video premise, stated as a hook>
- **Affiliate program:** yes / no / unknown — <signup URL if yes>
- **Claim status:** UNVERIFIED
```

Leave `Claim status` as `UNVERIFIED` always. It is promoted to `VERIFIED` only
by a human who has opened the page. That is the gate between research and
publishing, and this skill never crosses it.

### 4. Report
Output a short summary — the count, each finding's name and one-line angle,
and any contradictions flagged. Keep it under 200 words; the detail is in the
idea bank, not the message.

---

## Output template

```
NICHE RESEARCH — <today's date>
Findings: <n>  |  Searches run: <n>  |  Contradictions: <n>

1. <Tool/event> — <angle in one line>
2. <Tool/event> — <angle in one line>

⚠ <any contradiction, or omit this line>

Appended to idea bank. All claims UNVERIFIED pending manual check.
```

When there is nothing:

```
NICHE RESEARCH — <today's date>
NOTHING NEW TODAY. <n> searches run, no qualifying findings.
```

---

## Notes

- Cron runs set `skip_memory=True` by default, so findings will **not** enter
  agent memory. This is intentional: the idea bank file is the durable record.
- This skill only reads and appends. It never publishes, never posts, and
  never touches an affiliate account.
