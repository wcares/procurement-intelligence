"""Which models a user's request is using right now, so background work waits for those models only, not for the whole
app to be quiet (procintel.jobs.worker).

Every call to a model made for a user (procintel.core.llm, embed, decide) is wrapped in user_call(endpoint): the
endpoint counts as busy while the call runs and is remembered as last used when it ends. Calls made by background work
run inside llm.use_batch() and are not counted: a job does not wait for itself. A model is named by where it runs
(its address, or its name for a hosted one), so two settings that point at the same server are one model.
"""
from __future__ import annotations

import contextlib
import threading
import time
from typing import Iterable, Iterator

_lock = threading.Lock()
_running: dict[str, int] = {}        # endpoint -> user calls in progress
_last: dict[str, float] = {}         # endpoint -> when the last user call started or ended (time.monotonic)
clock = time.monotonic


def endpoint(model: str | None, base: str | None) -> str | None:
    return (base or model or None) and (base or model).rstrip("/")


def _in_background() -> bool:
    from procintel.core import llm
    return llm._in_batch.get()


@contextlib.contextmanager
def user_call(where: str | None) -> Iterator[None]:
    """Mark a model busy for the length of a call made for a user (background calls are not marked)."""
    if not where or _in_background():
        yield
        return
    with _lock:
        _running[where] = _running.get(where, 0) + 1
        _last[where] = clock()
    try:
        yield
    finally:
        with _lock:
            _running[where] -= 1
            _last[where] = clock()


def free_for(endpoints: Iterable[str | None]) -> float:
    """Seconds since any of these models last served a user (0 while one is serving; infinity if never)."""
    now, out = clock(), float("inf")
    with _lock:
        for e in filter(None, endpoints):
            if _running.get(e):
                return 0.0
            if e in _last:
                out = min(out, now - _last[e])
    return out


def used_since(t: float, endpoints: Iterable[str | None]) -> bool:
    """Whether a user call used one of these models after time t (clock())."""
    with _lock:
        return any(_running.get(e) or _last.get(e, -1.0) > t for e in filter(None, endpoints))


def background_endpoints() -> set[str]:
    """The models background work uses: the background model (or the answer model), embeddings, the decision model."""
    import os
    from procintel.core import decide, llm
    with llm.use_batch():
        talk = endpoint(llm.model_name(), llm._env(llm.ANSWER, "API_BASE"))
    embed = endpoint(os.environ.get("PROCINTEL_EMBED_MODEL"), os.environ.get("PROCINTEL_EMBED_API_BASE"))
    return {e for e in (talk, embed, endpoint(None, decide.api_base())) if e}


def state() -> dict[str, dict]:
    """For the queue panel: each model seen, whether it is serving a user now, and how long it has been free."""
    now = clock()
    with _lock:
        return {e: {"busy": bool(_running.get(e)), "freeSeconds": None if _running.get(e) else round(now - _last[e])}
                for e in _last}
