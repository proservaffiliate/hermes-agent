"""End-to-end tests for the Council MCP server. No network, no credentials."""
import asyncio, json, os, sys, tempfile, pathlib

TMP = tempfile.mkdtemp(prefix="council-test-")
os.environ["COUNCIL_HOME"] = TMP
for v in ("OPENAI_API_KEY","ANTHROPIC_API_KEY","GEMINI_API_KEY",
          "GOOGLE_API_KEY","OPENROUTER_API_KEY"):
    os.environ.pop(v, None)

import council_core as core, council_providers as providers, council_mcp as srv
from mcp.server.mcpserver.exceptions import ToolError

P=F=0
def check(label, cond, detail=""):
    global P,F
    if cond: P+=1; print(f"  PASS  {label}")
    else:    F+=1; print(f"  FAIL  {label} :: {detail}")

print(f"\ncouncil_home = {TMP}\n")

# 1 — thesis validation
print("thesis validation")
try:
    core.convene(decision="x", belief="b", reasoning="r", cost_dollars=1,
                 cost_hours=1, expected_return="e", refutation="  ", reversible=True)
    check("empty refutation rejected", False, "no error raised")
except ValueError as e:
    check("empty refutation rejected", "refutation" in str(e).lower())
try:
    core.convene(decision="  ", belief="b", reasoning="r", cost_dollars=1,
                 cost_hours=1, expected_return="e", refutation="ref", reversible=True)
    check("empty decision rejected", False, "no error raised")
except ValueError:
    check("empty decision rejected", True)

# 2 — convene
print("\nconvene")
s = core.convene(
    decision="Spend $25/mo on OpenRouter to automate the council",
    belief="Automation is what stops the council being abandoned",
    reasoning="Five manual pastes is friction and friction gets dropped",
    cost_dollars=25, cost_hours=6,
    expected_return="Council run in one command by 2026-10-15",
    refutation="If I still run it manually after 3 weeks, automation was not the blocker",
    reversible=True)
sid = s["id"]
check("session id generated", bool(sid), sid)
check("session.json written", (pathlib.Path(TMP)/"sessions"/sid/"session.json").exists())
prompts = core.all_seat_prompts(s)
check("five seat prompts", len(prompts)==5, str(len(prompts)))
check("mandates differ across seats", len({p[:400] for p in prompts.values()})==5)
check("thesis embedded in prompt", "OpenRouter" in prompts["red_team"])
check("anti-fabrication rule present", "UNVERIFIED" in prompts["evidence"])
check("red team mandate is adversarial", "post-mortem" in prompts["red_team"])

# 3 — unknown seat
try:
    core.seat("chairman"); check("unknown seat rejected", False)
except ValueError as e:
    check("unknown seat rejected", "Unknown seat" in str(e))

# 4 — path traversal
print("\npath safety")
for bad in ("../../etc", "a/b", ".hidden"):
    try:
        core._session_path(bad); check(f"rejects {bad!r}", False, "allowed")
    except ValueError:
        check(f"rejects {bad!r}", True)

# 5 — providers degrade, leak nothing
print("\nproviders")
av = providers.available()
check("all five providers listed", len(av)==5, str(list(av)))
check("ollama ready without key", av["ollama"]["ready"])
check("keyless providers not ready", not any(av[p]["ready"] for p in
      ("openai","anthropic","gemini","openrouter")))
os.environ["OPENAI_API_KEY"] = "sk-test-SHOULD-NEVER-APPEAR-1234567890"
blob = json.dumps(providers.available()) + json.dumps(srv.council_status())
check("no key material in status output", "SHOULD-NEVER-APPEAR" not in blob)
os.environ.pop("OPENAI_API_KEY")
try:
    providers.dispatch("openai", "hi"); check("NoCredential raised", False)
except providers.NoCredential:
    check("NoCredential raised", True)
try:
    providers.dispatch("nope", "hi"); check("unknown provider rejected", False)
except ValueError:
    check("unknown provider rejected", True)

# 6 — dispatch falls back to manual, does NOT fail
print("\ndispatch fallback")
d = srv.dispatch_seat(sid, "steelman")
check("status is manual not error", d["status"]=="manual", d["status"])
check("prompt returned for paste", "MY MANDATE" in d.get("prompt",""))
check("nothing recorded on fallback", len(core._read(sid)["responses"])==0)

# 7 — cross-examine guards
print("\ncross-examination")
try:
    core.cross_examination(sid); check("blocked with zero responses", False)
except ValueError as e:
    check("blocked with zero responses", "No seat responses" in str(e))

srv.record_seat_response(sid, "steelman", "1. POSITION - Proceed. Automation is the whole point.", model="antigravity")
srv.record_seat_response(sid, "red_team", "1. POSITION - Kill. You have published zero videos.", model="claude")
x = core.cross_examination(sid)
check("both responses present", "Proceed" in x and "Kill" in x)
check("attribution recorded", "antigravity" in x)
check("chair counsel appended", "load-bearing" in x)
check("missing seats named explicitly", "did not respond" in x and "NO RESPONSE RECORDED" in x)

# 8 — decision record
print("\ndecision record")
try:
    srv.record_decision(sid, "MAYBE", "x","x","x","x","2026-10-15")  # type: ignore
    check("invalid outcome rejected", False)
except ToolError as e:
    check("invalid outcome rejected", "must be one of" in str(e))

# server layer converts anticipated failures to ToolError so the message survives
print("\nerror surfacing")
for label, call in (
    ("unknown session -> ToolError", lambda: srv.cross_examine("nope")),
    ("unknown seat -> ToolError",    lambda: srv.record_seat_response(sid, "chair", "x")),
    ("empty response -> ToolError",  lambda: srv.record_seat_response(sid, "numbers", "  ")),
):
    try:
        call(); check(label, False, "no error raised")
    except ToolError as e:
        check(label, bool(str(e).strip()) and "Traceback" not in str(e))
    except Exception as e:
        check(label, False, f"wrong type {type(e).__name__}")
out = srv.record_decision(sid, decision="MODIFIED",
    chose="Try the free Gemini key first; spend the $25 only if grounding fails",
    overruled_seat="Steelman — automation is not the current bottleneck",
    load_bearing_bet="AI Studio's free tier includes search grounding",
    kill_trigger="Still pasting manually after 3 weeks",
    review_date="2026-10-16")
md = pathlib.Path(out["path"])
check("markdown record written", md.exists(), out["path"])
body = md.read_text()
check("outcome in record", "**MODIFIED**" in body)
check("overruled seat captured", "Steelman" in body)
check("review section present", "At review" in body)
check("seats heard listed", "The Steelman" in body and "The Red Team" in body)

# 9 — listing
print("\nlisting")
rows = core.list_sessions()
check("session listed", len(rows)==1, str(len(rows)))
check("outcome surfaced", rows[0]["outcome"]=="MODIFIED", rows[0]["outcome"])
check("seats counted", rows[0]["seats_heard"]==2, str(rows[0]["seats_heard"]))

# 10 — unknown session
try:
    core.cross_examination("nope-does-not-exist"); check("unknown session rejected", False)
except ValueError as e:
    check("unknown session rejected", "No council session" in str(e))

# 11 — MCP surface
print("\nMCP surface")
tools = asyncio.run(srv.mcp.list_tools())
check("seven tools exposed", len(tools)==7, str(len(tools)))
check("every tool documented", all((t.description or "").strip() for t in tools))
names = {t.name for t in tools}
check("expected tool names", names == {
    "council_status","convene_council","dispatch_seat","record_seat_response",
    "cross_examine","record_decision","list_council_sessions"}, str(names))

print(f"\n{'='*52}\n  {P} passed, {F} failed\n{'='*52}")
sys.exit(1 if F else 0)
