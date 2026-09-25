"""Council of Thought — usage and cost ledger.

Records what each model actually consumed, so the operator can see where
tokens and money go across the whole system.

Two honesty rules are built into this module and must not be relaxed:

  1. Token counts are only ever taken from what a provider actually returned.
     A call whose response carried no usage block is recorded with null
     token counts, not an estimate.

  2. Cost is computed only from rates the operator supplied in pricing.json.
     A model with no rate on file is recorded UNPRICED and excluded from
     totals. This module never guesses a price, because a plausible invented
     number is worse than a visible gap.

Subscription spend (Claude, ChatGPT, Gemini, Blotato) is flat and invisible
to token counting. Record it with add_fixed_cost so the picture is complete.

Storage: append-only JSONL at $COUNCIL_HOME/ledger/usage.jsonl
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from council_core import council_home


def _ledger_dir() -> Path:
    d = council_home() / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ledger_file() -> Path:
    return _ledger_dir() / "usage.jsonl"


def pricing_file() -> Path:
    return council_home() / "pricing.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ pricing

PRICING_TEMPLATE = {
    "_README": (
        "Rates in USD per 1,000,000 tokens. Fill these in from each "
        "provider's own current pricing page. Any model absent here is "
        "recorded UNPRICED and left out of cost totals — deliberately. "
        "Nothing in this system invents a rate."
    ),
    "_verified_on": None,
    "models": {},
}


def load_pricing() -> dict[str, Any]:
    p = pricing_file()
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(PRICING_TEMPLATE, indent=2), encoding="utf-8")
        return dict(PRICING_TEMPLATE)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(PRICING_TEMPLATE)


def rate_for(provider: str, model: str) -> Optional[dict[str, float]]:
    """Rate per 1M tokens for provider/model, or None if the operator has not
    supplied one. Keys tried: 'provider:model', then 'model'."""
    models = (load_pricing().get("models") or {})
    for key in (f"{provider}:{model}", model):
        r = models.get(key)
        if isinstance(r, dict) and ("input" in r or "output" in r):
            return {"input": float(r.get("input", 0.0)),
                    "output": float(r.get("output", 0.0))}
    return None


def _cost(provider: str, model: str,
          tin: Optional[int], tout: Optional[int]) -> tuple[Optional[float], str]:
    if tin is None and tout is None:
        return None, "NO_USAGE_REPORTED"
    rate = rate_for(provider, model)
    if rate is None:
        return None, "UNPRICED"
    usd = ((tin or 0) / 1_000_000 * rate["input"]
           + (tout or 0) / 1_000_000 * rate["output"])
    return round(usd, 6), "PRICED"


# ------------------------------------------------------------------ writing

def extract_usage(provider: str, payload: dict[str, Any]) -> dict[str, Optional[int]]:
    """Pull token counts out of a raw provider response. Returns None for a
    field the provider did not report — never a substitute figure.

    Field names follow each provider's documented response shape. They are
    not verified against a live API in this build; a shape change shows up as
    NO_USAGE_REPORTED rather than a wrong number.
    """
    try:
        if provider in ("openai", "openrouter"):
            u = payload.get("usage") or {}
            return {"input": u.get("prompt_tokens"), "output": u.get("completion_tokens")}
        if provider == "anthropic":
            u = payload.get("usage") or {}
            return {"input": u.get("input_tokens"), "output": u.get("output_tokens")}
        if provider == "gemini":
            u = payload.get("usageMetadata") or {}
            return {"input": u.get("promptTokenCount"), "output": u.get("candidatesTokenCount")}
        if provider == "ollama":
            return {"input": payload.get("prompt_eval_count"), "output": payload.get("eval_count")}
    except AttributeError:
        pass
    return {"input": None, "output": None}


def record(
    *, provider: str, model: str, tokens_in: Optional[int], tokens_out: Optional[int],
    seat: str = "", session_id: str = "", source: str = "dispatch", note: str = "",
) -> dict[str, Any]:
    usd, status = _cost(provider, model, tokens_in, tokens_out)
    entry = {
        "ts": _now(), "provider": provider, "model": model,
        "seat": seat, "session_id": session_id, "source": source,
        "tokens_in": tokens_in, "tokens_out": tokens_out,
        "cost_usd": usd, "cost_status": status, "note": note,
    }
    with ledger_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def add_fixed_cost(*, vendor: str, amount_usd: float, period: str, note: str = "") -> dict[str, Any]:
    """Record a flat subscription charge. Token counting cannot see these, and
    for this operation they are most of the real spend."""
    entry = {
        "ts": _now(), "provider": vendor, "model": "(subscription)",
        "seat": "", "session_id": "", "source": "fixed",
        "tokens_in": None, "tokens_out": None,
        "cost_usd": round(float(amount_usd), 2), "cost_status": "PRICED",
        "note": f"{period} — {note}".strip(" —"),
    }
    with ledger_file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


# ------------------------------------------------------------------ reading

def read_entries() -> list[dict[str, Any]]:
    f = ledger_file()
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn line must not take down the whole report
    return out


def report(since: str = "") -> dict[str, Any]:
    """Aggregate usage. Priced and unpriced are reported separately and never
    summed together — a total that silently swallows unpriced calls would
    understate real spend."""
    entries = [e for e in read_entries() if not since or e.get("ts", "") >= since]
    by_provider: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "tokens_in": 0, "tokens_out": 0,
                 "cost_usd": 0.0, "unpriced_calls": 0, "no_usage_calls": 0,
                 "models": set()})
    unpriced_models: set[str] = set()

    for e in entries:
        b = by_provider[e.get("provider", "unknown")]
        b["calls"] += 1
        b["tokens_in"] += e.get("tokens_in") or 0
        b["tokens_out"] += e.get("tokens_out") or 0
        b["models"].add(e.get("model", "?"))
        status = e.get("cost_status")
        if status == "PRICED":
            b["cost_usd"] += e.get("cost_usd") or 0.0
        elif status == "UNPRICED":
            b["unpriced_calls"] += 1
            unpriced_models.add(f"{e.get('provider')}:{e.get('model')}")
        else:
            b["no_usage_calls"] += 1

    providers = {}
    for k, v in by_provider.items():
        providers[k] = {**v, "models": sorted(v["models"]),
                        "cost_usd": round(v["cost_usd"], 4)}

    priced_total = round(sum(p["cost_usd"] for p in providers.values()), 4)
    unpriced_total = sum(p["unpriced_calls"] for p in providers.values())
    pricing = load_pricing()

    return {
        "entries": len(entries),
        "since": since or "(all time)",
        "providers": providers,
        "priced_total_usd": priced_total,
        "unpriced_calls": unpriced_total,
        "unpriced_models": sorted(unpriced_models),
        "pricing_verified_on": pricing.get("_verified_on"),
        "caveat": (
            "Covers only calls made through the council layer plus fixed costs "
            "recorded by hand. It is not a provider bill and does not see spend "
            "made outside this system."
            + (f" {unpriced_total} call(s) have no rate on file and are excluded "
               f"from the total." if unpriced_total else "")
        ),
    }
