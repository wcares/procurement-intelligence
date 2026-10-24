"""Single entry point for every LLM call. The model is configuration, not code.

Environment:
  PROCINTEL_LLM_MODEL     LiteLLM model string, e.g.
                            ollama/<your-qwen-tag>           local via Ollama
                            openai/<name>  + PROCINTEL_LLM_API_BASE=http://localhost:8080/v1
                                                              any OpenAI-compatible server (llama.cpp, mlx_lm, LM Studio, vLLM)
                            anthropic/claude-sonnet-5-5       Claude API (needs ANTHROPIC_API_KEY)
  PROCINTEL_LLM_API_BASE  optional endpoint override
  PROCINTEL_LLM_API_KEY   optional key for the endpoint
  PROCINTEL_LLM_EXTRA_BODY  optional JSON merged into the request body, for server-specific options, e.g.
                            {"chat_template_kwargs": {"enable_thinking": false}} so a reasoning model on llama.cpp
                            answers directly instead of spending the token budget on a hidden thinking block

If PROCINTEL_LLM_MODEL is unset, `available()` is False and callers must use their extractive fallback.
"""
from __future__ import annotations

import json
import os
from typing import Any


def model_name() -> str | None:
    return os.environ.get("PROCINTEL_LLM_MODEL") or None


def available() -> bool:
    return model_name() is not None


def complete(system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 1200, **kw: Any) -> str:
    """Return the assistant text. Raises if no model is configured; callers check available() first."""
    m = model_name()
    if m is None:
        raise RuntimeError("PROCINTEL_LLM_MODEL is not set")
    import litellm  # imported lazily: it is slow to import and not needed for retrieval-only paths

    extra = os.environ.get("PROCINTEL_LLM_EXTRA_BODY")
    if extra:
        kw.setdefault("extra_body", json.loads(extra))
    resp = litellm.completion(
        model=m,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
        api_base=os.environ.get("PROCINTEL_LLM_API_BASE"),
        api_key=os.environ.get("PROCINTEL_LLM_API_KEY"),
        **kw,
    )
    choice = resp.choices[0]
    if choice.finish_reason == "length":
        # a cut answer is not a short answer; for reasoning models this usually means the budget went to thinking
        raise RuntimeError(f"model output hit max_tokens={max_tokens} before finishing")
    return choice.message.content or ""
