"""API keys per model provider (Anthropic, OpenAI, Google Gemini, ...), saved once on the Settings page and used by
whichever model is switched to, so a switch never asks for a key again (procintel.core.llm).

A hosted model is named "<provider>/<model>" without an address of its own (anthropic/claude-sonnet-5-5); it gets its
provider's key. A model with an address is a server of our own (llama.cpp), and gets no provider key. Keys are kept in
data/provider_keys.json (owner-only, outside git), read on every call, and never sent back: status() says only which
providers have one.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from procintel.core import paths

PROVIDERS = {   # LiteLLM provider prefix -> name on the page (providers that need only an API key)
    "anthropic": "Anthropic (Claude)", "openai": "OpenAI", "gemini": "Google Gemini", "mistral": "Mistral",
    "groq": "Groq", "deepseek": "DeepSeek", "openrouter": "OpenRouter", "xai": "xAI (Grok)", "cohere": "Cohere",
    "together_ai": "Together AI", "fireworks_ai": "Fireworks AI", "perplexity": "Perplexity",
}
VALID = re.compile(r"^[\x21-\x7e]{8,512}$")
_lock = threading.Lock()


def path() -> Path:
    return paths.keys_dir() / "provider_keys.json"


def _read() -> dict[str, str]:
    f = path()
    return json.loads(f.read_text()) if f.exists() else {}


def _write(keys: dict[str, str]) -> None:
    f = path()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(keys))
    os.chmod(tmp, 0o600)
    tmp.replace(f)


def provider_of(model: str | None, base: str | None) -> str | None:
    """The provider whose key a model uses: its name's prefix, for a hosted model (no address of its own)."""
    if not model or base or "/" not in model:
        return None
    p = model.split("/", 1)[0].lower()
    return p if p in PROVIDERS else None


def get(provider: str | None) -> str | None:
    if not provider:
        return None
    with _lock:
        return _read().get(provider)


def put(provider: str, value: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"no provider {provider!r}; one of {', '.join(PROVIDERS)}")
    value = (value or "").strip()
    if not VALID.match(value):
        raise ValueError("a key is 8 to 512 characters without spaces")
    with _lock:
        keys = _read()
        keys[provider] = value
        _write(keys)


def remove(provider: str) -> None:
    with _lock:
        keys = _read()
        keys.pop(provider, None)
        _write(keys)


def status() -> list[dict]:
    """Every provider with whether a key is saved for it (never the key)."""
    with _lock:
        saved = _read()
    return [{"provider": p, "label": label, "set": p in saved} for p, label in PROVIDERS.items()]
