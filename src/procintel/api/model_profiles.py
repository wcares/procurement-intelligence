"""Model profiles: a saved answer model (name, address, extra options) that one click switches to on the Settings page.

Unlike the general profiles (procintel.api.config), a model profile holds only the model, so switching never changes
thresholds or other settings. The key comes from the provider's saved key (procintel.core.provider_keys), so a switch
needs nothing else. Kept in data/model_profiles.json; the first time, profiles that set an answer model are copied from
data/config_profiles.json, and a key saved for the answer model on the page (procintel.api.model_keys, the earlier
per-role keys) is moved to its provider.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from procintel.core import paths

FIELDS = {"model": "PROCINTEL_LLM_MODEL", "api_base": "PROCINTEL_LLM_API_BASE", "extra_body": "PROCINTEL_LLM_EXTRA_BODY"}
SETTING = {"model": "llm_model", "api_base": "llm_api_base", "extra_body": "llm_extra_body"}   # procintel.api.config keys


def path() -> Path:
    return paths.keys_dir() / "model_profiles.json"


def _read() -> dict[str, dict]:
    f = path()
    return json.loads(f.read_text()) if f.exists() else {}


def _write(all_: dict[str, dict]) -> None:
    path().parent.mkdir(parents=True, exist_ok=True)
    path().write_text(json.dumps(all_, indent=1))


def current() -> dict[str, str]:
    return {k: os.environ.get(var) or "" for k, var in FIELDS.items()}


def listing() -> list[dict]:
    """Saved model profiles, with the provider whose key each uses (None: a server of our own) and whether it is in use."""
    from procintel.core import provider_keys
    now = current()
    return [{"name": n, **p, "provider": provider_keys.provider_of(p["model"], p["api_base"] or None),
             "active": p["model"] == now["model"] and (p["api_base"] or "") == now["api_base"]}
            for n, p in sorted(_read().items())]


def save(name: str) -> list[dict]:
    """Save the answer model as it is set now under name (replacing a profile of that name)."""
    name = (name or "").strip()
    if not name or len(name) > 60:
        raise ValueError("a profile name of 1 to 60 characters is needed")
    now = current()
    if not now["model"]:
        raise ValueError("no answer model is set")
    all_ = _read()
    all_[name] = now
    _write(all_)
    return listing()


def apply(name: str) -> dict[str, str]:
    """Switch the answer model to a saved profile, kept after a restart; returns {setting: error} on failure."""
    from procintel.api import config
    p = _read().get(name)
    if p is None:
        return {"name": "no model profile with this name"}
    return config.update({SETTING[k]: p.get(k) or "" for k in FIELDS}, save=True)


def remove(name: str) -> bool:
    all_ = _read()
    if all_.pop(name, None) is None:
        return False
    _write(all_)
    return True


def migrate() -> None:
    """Once, at startup: copy model profiles from the general profiles, and move a page key of the answer model to
    its provider (so nothing has to be entered again)."""
    from procintel.api import model_keys
    from procintel.core import provider_keys
    if not path().exists() and paths.PROFILES_FILE.exists():
        old = json.loads(paths.PROFILES_FILE.read_text())
        _write({n: {k: str(v.get(SETTING[k]) or "") for k in FIELDS} for n, v in old.items() if v.get("llm_model")})
    page = model_keys._read()
    if "llm" in page:
        provider = provider_keys.provider_of(os.environ.get("PROCINTEL_LLM_MODEL"), os.environ.get("PROCINTEL_LLM_API_BASE"))
        if provider and not provider_keys.get(provider):
            provider_keys.put(provider, page["llm"])
        if provider:
            model_keys.remove("llm")    # the provider key serves it now; the .env key, if any, applies to local again
