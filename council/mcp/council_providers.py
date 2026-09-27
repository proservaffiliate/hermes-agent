"""Council of Thought — LLM connections.

Dispatches a seat prompt to a provider and returns the text.

CREDENTIAL BOUNDARY: this module never stores, writes, logs or asks for a key.
It reads them from the environment at call time. Populating the environment is
the job of the credential keeper (Codex's component), not this server.

If a provider has no credential, dispatch raises NoCredential and the caller
falls back to handing the prompt back for manual paste. The council therefore
works with zero keys configured on day one and upgrades to automatic dispatch
as keys appear.

Only the standard library is used, so there is nothing to install.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

TIMEOUT = float(os.environ.get("COUNCIL_HTTP_TIMEOUT", "120"))


class NoCredential(RuntimeError):
    """Provider has no usable credential in the environment."""


class ProviderError(RuntimeError):
    """Provider was reachable but the call failed."""


# Model ids are configurable because they change often. Override per provider
# with COUNCIL_<PROVIDER>_MODEL. Verify the defaults against the provider's
# current docs before relying on them.
PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "env": ("OPENAI_API_KEY",),
        "model_env": "COUNCIL_OPENAI_MODEL",
        "default_model": "gpt-5.5",
        "label": "OpenAI / ChatGPT",
    },
    "anthropic": {
        "env": ("ANTHROPIC_API_KEY",),
        "model_env": "COUNCIL_ANTHROPIC_MODEL",
        "default_model": "claude-opus-5",
        "label": "Anthropic / Claude",
    },
    "gemini": {
        "env": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "model_env": "COUNCIL_GEMINI_MODEL",
        "default_model": "gemini-3-pro",
        "label": "Google Gemini",
    },
    "openrouter": {
        "env": ("OPENROUTER_API_KEY",),
        "model_env": "COUNCIL_OPENROUTER_MODEL",
        "default_model": "google/gemini-3-pro",
        "label": "OpenRouter",
    },
    "ollama": {
        "env": (),  # local, no key
        "model_env": "COUNCIL_OLLAMA_MODEL",
        "default_model": "llama3.1:8b",
        "label": "Ollama (local)",
    },
}


def _key(provider: str) -> str:
    for var in PROVIDERS[provider]["env"]:
        val = os.environ.get(var, "").strip()
        if val:
            return val
    names = " or ".join(PROVIDERS[provider]["env"])
    raise NoCredential(f"{provider}: no credential in environment ({names})")


def model_for(provider: str) -> str:
    spec = PROVIDERS[provider]
    return os.environ.get(spec["model_env"], "").strip() or spec["default_model"]


def _post(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", **headers}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise ProviderError(f"HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise ProviderError(f"connection failed: {e.reason}") from None
    except json.JSONDecodeError:
        raise ProviderError("provider returned a non-JSON body") from None


def available() -> dict[str, dict[str, Any]]:
    """Which providers are usable right now. Never returns key material."""
    out = {}
    for name, spec in PROVIDERS.items():
        if name == "ollama":
            ok, why = True, "local — no credential needed (requires ollama running)"
        else:
            try:
                _key(name)
                ok, why = True, "credential present"
            except NoCredential as e:
                ok, why = False, str(e)
        out[name] = {
            "label": spec["label"],
            "ready": ok,
            "reason": why,
            "model": model_for(name),
        }
    return out


def dispatch(provider: str, prompt: str) -> dict[str, Any]:
    """Send prompt to provider. Raises NoCredential or ProviderError."""
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown provider {provider!r}. Known: {', '.join(PROVIDERS)}"
        )
    model = model_for(provider)

    if provider == "ollama":
        base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        data = _post(
            f"{base}/api/chat",
            {"model": model, "messages": [{"role": "user", "content": prompt}],
             "stream": False},
            {},
        )
        text = (data.get("message") or {}).get("content", "")

    elif provider == "gemini":
        key = _key(provider)
        base = os.environ.get(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"
        ).rstrip("/")
        data = _post(
            f"{base}/v1beta/models/{model}:generateContent",
            {"contents": [{"parts": [{"text": prompt}]}]},
            {"x-goog-api-key": key},
        )
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise ProviderError(f"unexpected response shape: {str(data)[:300]}") from None

    elif provider == "anthropic":
        key = _key(provider)
        base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
        data = _post(
            f"{base}/v1/messages",
            {"model": model, "max_tokens": 4096,
             "messages": [{"role": "user", "content": prompt}]},
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        try:
            text = "".join(b.get("text", "") for b in data["content"])
        except (KeyError, TypeError):
            raise ProviderError(f"unexpected response shape: {str(data)[:300]}") from None

    else:  # openai + openrouter share the chat-completions shape
        key = _key(provider)
        base = (
            os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            if provider == "openai"
            else os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        ).rstrip("/")
        data = _post(
            f"{base}/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": prompt}]},
            {"Authorization": f"Bearer {key}"},
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise ProviderError(f"unexpected response shape: {str(data)[:300]}") from None

    if not (text or "").strip():
        raise ProviderError("provider returned an empty response")
    return {"provider": provider, "model": model, "text": text.strip(),
            "raw": data}
