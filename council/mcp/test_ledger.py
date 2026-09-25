"""Ledger tests. The point of most of these is that the ledger REFUSES to guess."""
import os, json, tempfile, sys
os.environ["COUNCIL_HOME"] = tempfile.mkdtemp(prefix="ledger-test-")
import council_ledger as L, council_mcp as srv

P=F=0
def check(label, cond, detail=""):
    global P,F
    if cond: P+=1; print(f"  PASS  {label}")
    else:    F+=1; print(f"  FAIL  {label} :: {detail}")

print("\nusage extraction (real provider response shapes)")
check("openai", L.extract_usage("openai",{"usage":{"prompt_tokens":100,"completion_tokens":200}})=={"input":100,"output":200})
check("anthropic", L.extract_usage("anthropic",{"usage":{"input_tokens":10,"output_tokens":20}})=={"input":10,"output":20})
check("gemini", L.extract_usage("gemini",{"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":7}})=={"input":5,"output":7})
check("ollama", L.extract_usage("ollama",{"prompt_eval_count":1,"eval_count":2})=={"input":1,"output":2})
check("missing usage -> None not 0", L.extract_usage("openai",{})=={"input":None,"output":None})
check("garbage -> None not crash", L.extract_usage("anthropic",{"usage":"nonsense"})=={"input":None,"output":None})

print("\nrefusal to invent a price")
e = L.record(provider="openai", model="some-unpriced-model", tokens_in=1000, tokens_out=2000)
check("unpriced model -> UNPRICED", e["cost_status"]=="UNPRICED", e["cost_status"])
check("unpriced cost is null not a guess", e["cost_usd"] is None, str(e["cost_usd"]))
e2 = L.record(provider="openai", model="x", tokens_in=None, tokens_out=None)
check("no usage -> NO_USAGE_REPORTED", e2["cost_status"]=="NO_USAGE_REPORTED")
check("tokens stay null, not zeroed", e2["tokens_in"] is None)

print("\npricing supplied by the operator")
pf = L.pricing_file()
pf.write_text(json.dumps({"_verified_on":"2026-09-25",
    "models":{"openai:priced-model":{"input":1.0,"output":3.0}}}), encoding="utf-8")
e3 = L.record(provider="openai", model="priced-model", tokens_in=1_000_000, tokens_out=1_000_000)
check("priced correctly", e3["cost_status"]=="PRICED" and abs(e3["cost_usd"]-4.0)<1e-9, str(e3["cost_usd"]))
e4 = L.record(provider="openai", model="priced-model", tokens_in=500_000, tokens_out=0)
check("input-only maths", abs(e4["cost_usd"]-0.5)<1e-9, str(e4["cost_usd"]))

print("\nreport separates priced from unpriced")
r = L.report()
check("total counts only priced calls", abs(r["priced_total_usd"]-4.5)<1e-9, str(r["priced_total_usd"]))
check("unpriced calls surfaced", r["unpriced_calls"]==1, str(r["unpriced_calls"]))
check("unpriced model named", "openai:some-unpriced-model" in r["unpriced_models"])
check("caveat present", "not a provider bill" in r["caveat"])
check("pricing provenance shown", r["pricing_verified_on"]=="2026-09-25")

print("\nfixed subscription costs")
L.add_fixed_cost(vendor="Blotato", amount_usd=49.0, period="2026-09", note="base plan")
L.add_fixed_cost(vendor="Claude", amount_usd=20.0, period="2026-09")
r2 = L.report()
check("subscriptions included", abs(r2["priced_total_usd"]-(4.5+69.0))<1e-9, str(r2["priced_total_usd"]))
check("vendor tracked separately", "Blotato" in r2["providers"])
check("subscription has no token counts", r2["providers"]["Blotato"]["tokens_in"]==0)

print("\nrobustness")
with L.ledger_file().open("a") as f: f.write("{ this is a torn line\n")
check("torn line skipped, report survives", L.report()["entries"]>=6)

print("\nMCP surface")
rep = srv.usage_report()
check("usage_report returns a report", "priced_total_usd" in rep)
fx = srv.record_fixed_cost("Gemini", 20.0, "2026-09")
check("record_fixed_cost works", fx["cost_usd"]==20.0)
ex = srv.record_external_usage("antigravity","gemini-3-pro",1200,800,seat="evidence")
check("external usage recorded", ex["source"]=="external" and ex["tokens_in"]==1200)
check("external unpriced flagged", ex["cost_status"]=="UNPRICED")

print(f"\n{'='*52}\n  {P} passed, {F} failed\n{'='*52}")
sys.exit(1 if F else 0)
