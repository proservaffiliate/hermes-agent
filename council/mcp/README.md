# Council of Thought — MCP server

Turns the five-seat decision council into MCP tools, so any MCP client —
Antigravity, Claude Code, Claude Desktop, Hermes — can convene it.

It exists to remove the one thing that kills the protocol: five manual
copy-pastes per decision. Friction gets abandoned.

---

## Division of the work

| Component | Owner | Responsibility |
|---|---|---|
| Credential keeper + Antigravity link | **Codex** | Stores keys, puts them in the environment |
| Council structure + LLM connections | **This server** | Seats, prompts, dispatch, cross-examination, decision records |

**This server never stores, writes, logs or asks for an API key.** It reads
them from the environment at call time. That keeps one source of truth for
credentials — the keeper — and means this repo can be shared or committed
without leaking anything.

It also means **the council works with zero credentials configured.** A seat
with no key returns its prompt for manual paste instead of failing. As Codex
lands keys, seats flip from manual to automatic with no change here.

---

## Install

```bash
pip install -r requirements.txt          # only dependency: mcp>=2
python3 test_council.py                  # 43 unit checks
python3 test_protocol.py                 # live MCP handshake over stdio
```

Both should exit 0 before you wire it into anything.

## Register it

Same JSON shape in every client. In **Antigravity**, add it through its MCP
settings; in **Claude Code**, `.mcp.json` in the project root or
`claude mcp add`; in **Claude Desktop**, `claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "council": {
      "command": "python3",
      "args": ["/ABSOLUTE/PATH/TO/council-mcp/council_mcp.py"],
      "env": {
        "COUNCIL_HOME": "/ABSOLUTE/PATH/TO/your/council-records"
      }
    }
  }
}
```

Credentials are deliberately absent from that block. Let the keeper put
`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` and `OLLAMA_BASE_URL`
into the environment the client launches with.

---

## The seats

| Seat | Default provider | Mandate |
|---|---|---|
| `steelman` | openai | Strongest version of the idea — assume it worked, say what had to be true |
| `red_team` | anthropic | Assume it failed at 12 months; write the post-mortem |
| `evidence` | gemini | What is verifiably true right now, with URLs and dates |
| `numbers` | anthropic | Cost to first dollar, break-even, what the founder isn't counting |
| `operator` | ollama | Can this be built in 1–2 hrs/day on this budget? |

Override any seat's model with `provider` on `dispatch_seat`, or seat a model
this server can't reach (Antigravity) via `record_seat_response`.

Model ids default conservatively and are overridable:
`COUNCIL_OPENAI_MODEL`, `COUNCIL_ANTHROPIC_MODEL`, `COUNCIL_GEMINI_MODEL`,
`COUNCIL_OPENROUTER_MODEL`, `COUNCIL_OLLAMA_MODEL`. **Check the defaults
against each provider's current docs** — model names change often and these
were not verified against a live API.

---

## Wiring it into Hermes

Hermes can convene the council itself — on a cron schedule, from Telegram, or
in the TUI. One command from the repo root:

```bash
bash council/wire-hermes.sh
```

It installs the `mcp>=2` dependency, verifies the server imports, registers it
with `hermes mcp add`, installs the `council-protocol` skill so Hermes knows
when to convene and who decides, and runs `hermes mcp test council`. Re-running
it will not create a duplicate.

Verify:

```bash
hermes mcp list          # 'council' present
hermes mcp test council  # connection OK
```

**No credentials are passed during wiring, deliberately.** The server reads
provider keys from the environment at call time, so whatever the keeper puts in
Hermes's environment is what the seats use. Putting a key in the wiring would
fork the source of truth.

One gotcha if you register it by hand: `hermes mcp add` takes `--args` as
`argparse.REMAINDER`, so it must be the **last** option on the line — anything
after it is swallowed as command argv.

To register declaratively instead, the equivalent block in `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  council:
    command: /usr/bin/python3
    args: [/ABSOLUTE/PATH/TO/council/mcp/council_mcp.py]
    env:
      COUNCIL_HOME: /ABSOLUTE/PATH/TO/council-records
      PYTHONPATH: /ABSOLUTE/PATH/TO/council/mcp
```

---

## Running a council

1. `council_status` — see which seats will dispatch and which need paste
2. `convene_council` — Founder Thesis in, five seat prompts out
3. `dispatch_seat` × 5 — automatic where a key exists, prompt returned where not
4. `record_seat_response` — for any seat answered by hand or by Antigravity
5. `cross_examine` — **never skip this**; it's what turns five opinions into a decision
6. `record_decision` — writes `DECISION-NNN.md`

Convene only for a commitment over **$100 or ten hours**, a **change of
direction**, or the **monthly review**. Everything smaller: just do it.

Records land in `$COUNCIL_HOME` (default `~/council`) as markdown. Commit them
to git. Within three months that folder shows which seat is reliably right for
you — and which of your own overruled instincts keep turning out correct.

---

## One design warning

You've said Antigravity will **both drive the council and take a seat.** That
works mechanically — drive with the tools, answer via `record_seat_response`
— but it is a real weakness, not a detail.

A model that chairs the session and argues a seat in it is reviewing its own
argument. Chair's counsel is supposed to name where the seats genuinely
conflict; a chair with a position in the fight has an interest in the answer.

Two ways to keep the protocol honest:

- **Preferred:** Antigravity drives, but the Chair is you. Run
  `cross_examine`, read the conflict yourself, and call `record_decision` with
  your decision. The tool description says as much: a model calling it is
  recording the founder's decision, not making one.
- **If Antigravity must synthesise:** have it take a seat it is least invested
  in, and record its seat answer *before* it sees the others. `cross_examine`
  names every seat that didn't respond, so order is auditable after the fact.

Never let the seat it argued be the one it overrules in the record.

---

## What is not here, deliberately

No database, no audit log, no role enforcement, no publishing.

Role enforcement was considered and rejected on purpose. In stdio MCP the
caller supplies every argument, so any `actor` field is self-asserted — a
model can simply claim to be the Chair. A check on that field would look like
security while providing none. Records carry a `model` field that says who
answered, recorded honestly rather than enforced, and the trust boundary is
the human reading the record.
