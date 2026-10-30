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

A model for the background jobs (tagging passages, evaluations, prompt tests) is set with PROCINTEL_BATCH_MODEL,
PROCINTEL_BATCH_API_BASE, PROCINTEL_BATCH_API_KEY and PROCINTEL_BATCH_EXTRA_BODY. While a job runs (use_batch()), every call
that would go to the answer model goes there instead; a setting left empty falls back to the answer model's, so with none
set the jobs use the answer model as before. When the batch model is another endpoint or model (batch_dedicated()), jobs
no longer compete with users' requests and the worker does not make them wait for quiet (procintel.jobs.worker).

A second model, the independent judge of the evaluation, is set the same way with PROCINTEL_JUDGE_MODEL,
PROCINTEL_JUDGE_API_BASE, PROCINTEL_JUDGE_API_KEY and PROCINTEL_JUDGE_EXTRA_BODY; calls pass prefix=JUDGE.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import os
from typing import Any, Iterator


ANSWER = "PROCINTEL_LLM"
JUDGE = "PROCINTEL_JUDGE"
BATCH = "PROCINTEL_BATCH"
_in_batch: contextvars.ContextVar[bool] = contextvars.ContextVar("llm_in_batch", default=False)


@contextlib.contextmanager
def use_batch():
    """Inside this block (a background job), calls for the answer model go to the batch model where one is set."""
    token = _in_batch.set(True)
    try:
        yield
    finally:
        _in_batch.reset(token)


def _env(prefix: str, name: str) -> str | None:
    """One setting of a model. For the answer model inside a background job this is the batch model's, field by field: a
    field left empty is the answer model's, except that a key or extra options are not handed to a different endpoint or model."""
    if prefix == ANSWER and _in_batch.get():
        own = os.environ.get(f"{BATCH}_{name}") or None
        if own is not None:
            return own
        if name == "API_KEY" and (os.environ.get(f"{BATCH}_API_BASE") or None) not in (None, os.environ.get(f"{ANSWER}_API_BASE") or None):
            return None   # the answer model's key stays with the answer model's endpoint
        if name == "EXTRA_BODY" and (os.environ.get(f"{BATCH}_MODEL") or None) not in (None, os.environ.get(f"{ANSWER}_MODEL") or None):
            return None   # options written for one model do not belong to another
    return os.environ.get(f"{prefix}_{name}") or None


def batch_dedicated() -> bool:
    """True when background jobs have a model of their own: another endpoint or another model than the answer model."""
    model, base = os.environ.get(f"{BATCH}_MODEL") or None, os.environ.get(f"{BATCH}_API_BASE") or None
    return bool((base and base != (os.environ.get(f"{ANSWER}_API_BASE") or None))
                or (model and model != (os.environ.get(f"{ANSWER}_MODEL") or None)))


def model_name(prefix: str = ANSWER) -> str | None:
    return _env(prefix, "MODEL")


def available(prefix: str = ANSWER) -> bool:
    return model_name(prefix) is not None


TEMPERATURE = 0.0  # defaults for every call; tunable at runtime through procintel.api.config
MAX_TOKENS = 1200


def _request(system: str, user: str, temperature: float | None, max_tokens: int | None, prefix: str, kw: dict) -> dict:
    """The litellm.completion arguments shared by complete() and stream()."""
    m = model_name(prefix)
    if m is None:
        raise RuntimeError(f"{prefix}_MODEL is not set")
    max_tokens = MAX_TOKENS if max_tokens is None else max_tokens
    kw.setdefault("drop_params", True)  # a model that fixes its own temperature (Claude 5.5) must not fail on ours
    extra = _env(prefix, "EXTRA_BODY")
    if extra:
        kw.setdefault("extra_body", json.loads(extra))
    return dict(model=m, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=TEMPERATURE if temperature is None else temperature, max_tokens=max_tokens,
                api_base=_env(prefix, "API_BASE"), api_key=_env(prefix, "API_KEY"), **kw)


def _cut(max_tokens: int | None) -> RuntimeError:
    # a cut answer is not a short answer; for reasoning models this usually means the budget went to thinking
    return RuntimeError(f"model output hit max_tokens={MAX_TOKENS if max_tokens is None else max_tokens} before finishing")


def complete(system: str, user: str, *, temperature: float | None = None, max_tokens: int | None = None,
             prefix: str = ANSWER, **kw: Any) -> str:
    """Return the assistant text. Raises if no model is configured; callers check available() first."""
    args = _request(system, user, temperature, max_tokens, prefix, kw)
    import litellm  # imported lazily: it is slow to import and not needed for retrieval-only paths

    choice = litellm.completion(**args).choices[0]
    if choice.finish_reason == "length":
        raise _cut(max_tokens)
    return choice.message.content or ""


def stream(system: str, user: str, *, temperature: float | None = None, max_tokens: int | None = None,
           prefix: str = ANSWER, **kw: Any) -> Iterator[str]:
    """The assistant text in pieces, as the model writes it. Same settings and failures as complete()."""
    args = _request(system, user, temperature, max_tokens, prefix, kw)
    import litellm

    for chunk in litellm.completion(stream=True, **args):
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.delta and choice.delta.content:
            yield choice.delta.content
        if choice.finish_reason == "length":
            raise _cut(max_tokens)
