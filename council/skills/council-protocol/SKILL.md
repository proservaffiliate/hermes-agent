---
name: council-protocol
description: How to run the Council of Thought — when to convene it, the order of the steps, and who decides. Use whenever a decision involves real money, real time, or a change of direction.
version: 1.0.0
author: Founder
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [council, decision, governance, strategy]
    category: research
---

# Council of Thought

The `council` MCP server exposes the tools. This skill is the protocol they
serve. Tools without the protocol produce five opinions; the protocol produces
a decision.

---

## Convene only on three triggers

1. A commitment over **$100** or over **ten hours** of founder time
2. A **change of direction** — niche, positioning, platform, offer, pricing
3. The **monthly review**, where the thesis examined is the last thirty days

Anything smaller: just do it and say so. Speed on reversible decisions is an
advantage, and a council convened over a $12 tool is how the protocol stops
being used at all.

---

## Who decides

**The founder is Chair. That is never delegated to a model, including you.**

You route, convene, synthesise and record. You do not decide. When you call
`record_decision`, you are writing down a decision the founder made — never
one you reached. If the founder has not stated a decision, ask for it; do not
supply one.

A council that decides for the founder is not a check on the founder. It is
one model with extra steps, and it removes the only reason this system exists.

---

## The order

**1. Founder Thesis.** Get all of it before calling anything. `convene_council`
rejects an empty refutation on purpose — an idea with no refutation condition
is a preference, and a preference cannot be tested.

- Decision on the table — an action, not a topic
- What the founder believes, and the real reason including the emotional one
- Cost in dollars and hours
- Expected return — a number and a date
- **How they will know they were wrong** — a specific observable
- Reversible?

**2. `council_status`.** See which seats dispatch automatically and which need
a paste. Report that before starting, so nobody waits on a seat that was never
going to answer.

**3. `convene_council`.** Returns a session id and five seat prompts.

**4. `dispatch_seat` × 5.** Each seat argues one mandate:

| Seat | Mandate |
|---|---|
| `steelman` | The strongest version. Assume it worked; say what had to be true. |
| `red_team` | Assume it failed at twelve months. Write the post-mortem. |
| `evidence` | What is verifiably true now, with URLs and dates. |
| `numbers` | Cost to first dollar, break-even, what is not being counted. |
| `operator` | Can it be built in 1–2 hrs/day on this budget? |

A seat that returns `status: manual` has no credential. Hand the prompt to the
founder, then record the reply with `record_seat_response`. Record who actually
answered in the `model` field, honestly.

**5. `cross_examine`. Never skip this.** It returns every response plus the
Chair's-counsel prompt that surfaces real disagreement. Run that prompt and
give the founder the synthesis: where the seats genuinely conflict, which
agreement is shared assumption rather than shared evidence, and which single
claim breaks the most others if false.

Unanswered seats are named explicitly in the output. Never read silence as
agreement.

**6. `record_decision`.** After the founder decides. The `overruled_seat` field
is the point of the whole record — over months it shows which of the founder's
overruled instincts keep turning out right.

---

## Rules

- **Never invent a seat's answer.** If a seat did not respond, it did not respond.
- **Never present unretrieved information as fact.** `UNVERIFIED` is always an
  acceptable answer. Invented is never one.
- **Never skip cross-examination** because the seats seem to agree. Apparent
  agreement is the case most worth examining.
- **Never call `record_decision`** without a decision from the founder.
- Check `usage_report` after a full council so the founder sees what it cost.
  Unpriced calls are excluded from totals rather than estimated — say so rather
  than implying the total is complete.

---

## Cost

A five-seat council is five model calls plus a synthesis. Route seats to the
models the server already assigns them; do not upgrade a seat to a more
expensive model to "get a better answer." The mandate does the work, not the
model tier.
