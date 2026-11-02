"""API keys for the models, set from the Settings page: write-only, so a cloud model can be switched to without editing
.env or restarting.

A key set here is kept in data/model_keys.json (readable by the owner only, outside git) and put into the process
environment, where procintel.core.llm reads it on every call, so the next request uses it. It is never sent back:
status() says only whether a key is set and where it comes from (this page or the environment). Removing a page key
brings back the one from .env, if there was one. Keys in .env keep working as before.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from procintel.core import paths

ROLES = {   # the model each key belongs to, and the environment variable procintel.core.llm reads
    "llm": "PROCINTEL_LLM_API_KEY",       # answer model
    "judge": "PROCINTEL_JUDGE_API_KEY",   # second checking model (evaluation)
    "batch": "PROCINTEL_BATCH_API_KEY",   # model for background work
}
VALID = re.compile(r"^[\x21-\x7e]{8,512}$")   # printable, no spaces: a key, not a sentence pasted by mistake
_from_env: dict[str, str | None] = {}           # what the environment held before a page key replaced it


def path() -> Path:
    return paths.keys_dir() / "model_keys.json"


def _read() -> dict[str, str]:
    f = path()
    return json.loads(f.read_text()) if f.exists() else {}


def _write(keys: dict[str, str]) -> None:
    f = path()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(keys))
    os.chmod(tmp, 0o600)          # owner only, before it holds the real name
    tmp.replace(f)


def _apply(role: str, value: str | None) -> None:
    var = ROLES[role]
    if role not in _from_env:
        _from_env[role] = os.environ.get(var)
    if value is not None:
        os.environ[var] = value
    elif _from_env[role]:
        os.environ[var] = _from_env[role]
    else:
        os.environ.pop(var, None)


def load() -> None:
    """At startup: page keys over those from the environment."""
    for role, value in _read().items():
        if role in ROLES:
            _apply(role, value)


def status() -> dict[str, dict]:
    page = _read()
    return {role: {"set": bool(os.environ.get(var)),
                   "from": "page" if role in page else "environment" if os.environ.get(var) else None}
            for role, var in ROLES.items()}


def put(role: str, value: str) -> None:
    if role not in ROLES:
        raise ValueError(f"no model {role!r}; one of {', '.join(ROLES)}")
    value = (value or "").strip()
    if not VALID.match(value):
        raise ValueError("a key is 8 to 512 characters without spaces")
    keys = _read()
    keys[role] = value
    _write(keys)
    _apply(role, value)


def remove(role: str) -> None:
    if role not in ROLES:
        raise ValueError(f"no model {role!r}; one of {', '.join(ROLES)}")
    keys = _read()
    keys.pop(role, None)
    _write(keys)
    _apply(role, None)
