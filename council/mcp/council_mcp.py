#!/usr/bin/env python3
"""Council of Thought — MCP server.

Exposes the five-seat decision council as MCP tools so any MCP client
(Antigravity, Claude Code, Hermes, Claude Desktop) can convene it.

Credential boundary: this server never stores, writes, logs or asks for an
API key. It reads them from the environment at call time. Populating the
environment is the credential keeper's job, not this server's. If a key is
absent, the seat prompt comes back for manual paste instead of failing — so
the council works with zero credentials configured and upgrades to automatic
dispatch as keys appear.

Run:  python3 council_mcp.py
"""
from __future__ import annotations

from typing import Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

import council_core as core
import council_providers as providers

import functools


def expected_errors(fn):
    """Turn anticipated failures into ToolError so the calling agent gets the
    message instead of a stack trace. Bad session ids and unknown seats are
    ordinary, correctable mistakes — the error text is the agent's only
    guidance, so it has to survive the trip."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except (ValueError, KeyError) as e:
            raise ToolError(str(e)) from e
    return wrapper


SeatKey = Literal["steelman", "red_team", "evidence", "numbers", "operator"]
ProviderKey = Literal["openai", "anthropic", "gemini", "openrouter", "ollama"]
Outcome = Literal["PROCEED", "MODIFIED", "KILL"]

mcp = MCPServer(
    name="council-of-thought",
    version="1.0.0",
    instructions=(
        "A five-seat decision council. Each seat argues one mandate against "
        "the founder's thesis; the founder reads the conflict and decides as "
        "Chair. Convene only for a commitment over $100 or ten hours, a change "
        "of direction, or the monthly review — everything smaller should just "
        "be done. Never skip cross_examine: five separate opinions are not a "
        "decision. The Chair is the founder; a model calling record_decision "
        "is recording their decision, not making one."
    ),
)


@mcp.tool()
@expected_errors
def council_status() -> dict[str, Any]:
    """Which LLM providers the council can reach right now and which seat each
    one holds. Returns no key material. Call this first to see whether seats
    will dispatch automatically or need manual paste."""
    return {
        "providers": providers.available(),
        "seats": [
            {"seat": s.key, "name": s.name,
             "default_provider": s.default_provider, "mandate": s.mandate}
            for s in core.SEATS
        ],
        "council_home": str(core.council_home()),
    }


@mcp.tool()
@expected_errors
def convene_council(
    decision: str,
    belief: str,
    reasoning: str,
    cost_dollars: float,
    cost_hours: float,
    expected_return: str,
    refutation: str,
    reversible: bool,
) -> dict[str, Any]:
    """Open a council session from a Founder Thesis and return the five seat
    prompts.

    decision: one sentence, an action not a topic.
    belief: the founder's actual position, stated plainly.
    reasoning: the real reason, including the emotional one.
    expected_return: a number and a date.
    refutation: the specific observable that would prove the thesis wrong.
        Required — an idea with no refutation condition is a preference, and
        the council cannot test a preference.
    """
    session = core.convene(
        decision=decision, belief=belief, reasoning=reasoning,
        cost_dollars=cost_dollars, cost_hours=cost_hours,
        expected_return=expected_return, refutation=refutation,
        reversible=reversible,
    )
    return {
        "session_id": session["id"],
        "thesis": core.thesis_block(session),
        "seat_prompts": core.all_seat_prompts(session),
        "next": ("Dispatch each seat with dispatch_seat, or paste the prompts "
                 "into the models yourself and use record_seat_response. "
                 "Then cross_examine."),
    }


@mcp.tool()
@expected_errors
def dispatch_seat(
    session_id: str, seat: SeatKey, provider: ProviderKey | None = None
) -> dict[str, Any]:
    """Send one seat's prompt to its LLM and record the reply.

    If that provider has no credential, returns the prompt to paste manually
    rather than failing. Pass provider to override the seat's default — for
    example to seat a different model in the Evidence chair.
    """
    session = core._read(session_id)
    prov = provider or core.seat(seat).default_provider
    prompt = core.seat_prompt(session, seat)
    try:
        result = providers.dispatch(prov, prompt)
    except providers.NoCredential as e:
        return {"status": "manual", "seat": seat, "reason": str(e),
                "prompt": prompt,
                "next": "Paste this into that model, then call "
                        "record_seat_response with its reply."}
    except providers.ProviderError as e:
        return {"status": "error", "seat": seat, "provider": prov,
                "error": str(e), "prompt": prompt,
                "next": "Provider was reachable but the call failed. Fall back "
                        "to manual paste, or fix and retry."}
    core.record_response(session_id, seat, result["text"],
                         model=f"{prov}:{result['model']}")
    return {"status": "recorded", "seat": seat, "provider": prov,
            "model": result["model"], "response": result["text"]}


@mcp.tool()
@expected_errors
def record_seat_response(
    session_id: str, seat: SeatKey, response: str, model: str = "manual"
) -> dict[str, Any]:
    """Record a seat's answer obtained outside this server — pasted from a chat
    window, or produced by the calling agent taking that seat itself.

    model: who actually answered, e.g. 'antigravity'. Record it honestly; the
    decision record is only worth keeping if it says who said what.
    """
    core.record_response(session_id, seat, response, model=model)
    return {"status": "recorded", "seat": seat, "model": model}


@mcp.tool()
@expected_errors
def cross_examine(session_id: str) -> str:
    """Return every recorded seat response plus the Chair's-counsel prompt that
    surfaces genuine disagreement.

    This is the step that turns five opinions into a decision. Skipping it
    leaves the founder averaging five confident answers, which is mush.
    Unanswered seats are named explicitly so silence is not read as agreement.
    """
    return core.cross_examination(session_id)


@mcp.tool()
@expected_errors
def record_decision(
    session_id: str,
    decision: Outcome,
    chose: str,
    overruled_seat: str,
    load_bearing_bet: str,
    kill_trigger: str,
    review_date: str,
) -> dict[str, Any]:
    """Close the session with the Chair's decision and write a Decision Record
    markdown file.

    overruled_seat: which seat was decided against, and why. This field is the
        point of the whole record — over time it shows which of the founder's
        overruled instincts keep turning out right.
    kill_trigger: the observable that means stop.
    review_date: YYYY-MM-DD.
    """
    return {"status": "recorded",
            **core.record_decision(
                session_id, decision=decision, chose=chose,
                overruled_seat=overruled_seat,
                load_bearing_bet=load_bearing_bet,
                kill_trigger=kill_trigger, review_date=review_date)}


@mcp.tool()
@expected_errors
def list_council_sessions() -> dict[str, Any]:
    """Past and open council sessions, newest first, with outcomes and review
    dates. Sessions reading OPEN were convened but never decided."""
    return {"sessions": core.list_sessions()}


if __name__ == "__main__":
    mcp.run(transport="stdio")
