"""Live MCP protocol test: launches council_mcp.py over stdio and talks to it."""
import asyncio, os, sys, tempfile, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TMP = tempfile.mkdtemp(prefix="council-proto-")

async def main():
    env = {**os.environ, "COUNCIL_HOME": TMP}
    for v in ("OPENAI_API_KEY","ANTHROPIC_API_KEY","GEMINI_API_KEY","GOOGLE_API_KEY"):
        env.pop(v, None)
    params = StdioServerParameters(
        command=sys.executable, args=["council_mcp.py"], env=env, cwd=os.getcwd()
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print(f"handshake OK -> {init.server_info.name} v{init.server_info.version}")

            tools = (await s.list_tools()).tools
            print(f"list_tools    -> {len(tools)} tools: {', '.join(t.name for t in tools)}")
            assert len(tools) == 10

            st = await s.call_tool("council_status", {})
            data = json.loads(st.content[0].text)
            print(f"council_status-> {len(data['providers'])} providers, {len(data['seats'])} seats")
            assert len(data["seats"]) == 5

            cv = await s.call_tool("convene_council", {
                "decision": "Ship the council MCP to Antigravity today",
                "belief": "The structure is the deliverable, not the automation",
                "reasoning": "Codex owns credentials; I own structure and LLM links",
                "cost_dollars": 0, "cost_hours": 3,
                "expected_return": "Council convenable from Antigravity by noon",
                "refutation": "If Antigravity cannot call the tools, the design is wrong",
                "reversible": True})
            sid = json.loads(cv.content[0].text)["session_id"]
            print(f"convene       -> session {sid}")

            dz = await s.call_tool("dispatch_seat", {"session_id": sid, "seat": "evidence"})
            dd = json.loads(dz.content[0].text)
            print(f"dispatch_seat -> status={dd['status']} (graceful, no credential)")
            assert dd["status"] == "manual" and "MY MANDATE" in dd["prompt"]

            await s.call_tool("record_seat_response", {
                "session_id": sid, "seat": "evidence",
                "response": "1. POSITION - No public evidence of a comparable five-model council protocol. UNVERIFIED beyond search.",
                "model": "antigravity"})
            await s.call_tool("record_seat_response", {
                "session_id": sid, "seat": "operator",
                "response": "1. POSITION - Buildable. Three hours, no new spend.",
                "model": "ollama:llama3.1:8b"})
            print("record x2     -> ok")

            xe = await s.call_tool("cross_examine", {"session_id": sid})
            text = xe.content[0].text
            print(f"cross_examine -> {len(text)} chars, names missing seats: {'did not respond' in text}")
            assert "antigravity" in text and "did not respond" in text

            rd = await s.call_tool("record_decision", {
                "session_id": sid, "decision": "PROCEED",
                "chose": "Ship it; Codex wires credentials separately",
                "overruled_seat": "None - no seat dissented",
                "load_bearing_bet": "Antigravity can register a stdio MCP server",
                "kill_trigger": "Antigravity cannot load it by end of day",
                "review_date": "2026-10-02"})
            path = json.loads(rd.content[0].text)["path"]
            print(f"record_decision-> {path}")
            assert os.path.exists(path)

            ur = await s.call_tool("usage_report", {})
            urd = json.loads(ur.content[0].text)
            print(f"usage_report  -> {urd['entries']} entries, priced ${urd['priced_total_usd']}, caveat present={'not a provider bill' in urd['caveat']}")
            assert "not a provider bill" in urd["caveat"]

            ls = await s.call_tool("list_council_sessions", {})
            rows = json.loads(ls.content[0].text)["sessions"]
            print(f"list_sessions -> {len(rows)} session, outcome={rows[0]['outcome']}")
            assert rows[0]["outcome"] == "PROCEED"

            try:
                err = await s.call_tool("cross_examine", {"session_id": "no-such-session"})
                blob = (err.content[0].text if err.content else "") + str(getattr(err, "isError", ""))
            except Exception as e:
                blob = str(e)
            assert "No council session" in blob, f"error message lost over the wire: {blob[:200]}"
            assert "Traceback" not in blob, "stack trace leaked to client"
            print("error path    -> clean message reached client, no stack trace")

    print("\nALL PROTOCOL CHECKS PASSED")

asyncio.run(main())
