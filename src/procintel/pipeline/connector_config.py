"""Connector settings by configuration: each source's mode, read interval and on/off, saved to the data folder
(paths.CONNECTORS_FILE) from the Connectors page; a source with no saved settings uses its defaults from
procintel.pipeline.entities. The code still says how to read a source (its reader); configuration says when and whether.

    mode      poll: read on its interval (every source today); push: the source posts changes to the webhook
              (procintel.pipeline.webhook) and polling stops, apart from a daily reconciliation read
    every     hours between reads (polling), at least MIN_HOURS
    enabled   off: never read on schedule (a "Read now" still reads it)
"""
from __future__ import annotations

import json
from datetime import timedelta

from procintel.core import paths
from procintel.pipeline import entities

MODES = ("poll", "push")
MIN_HOURS = 0.25
PUSH_RECONCILE = timedelta(days=1)   # a pushed source is still read this often, to catch pushes lost while down


def _saved() -> dict:
    f = paths.CONNECTORS_FILE
    return json.loads(f.read_text()) if f.exists() else {}


def settings(name: str) -> dict:
    et = entities.ENTITY_TYPES[name]
    default = {"mode": et.mode, "everyHours": et.every.total_seconds() / 3600, "enabled": True}
    return default | {k: v for k, v in _saved().get(name, {}).items() if k in default}


def defaults(name: str) -> dict:
    et = entities.ENTITY_TYPES[name]
    return {"mode": et.mode, "everyHours": et.every.total_seconds() / 3600, "enabled": True}


def every(et: entities.EntityType) -> timedelta:
    s = settings(et.name)
    return PUSH_RECONCILE if s["mode"] == "push" else timedelta(hours=s["everyHours"])


def enabled(name: str) -> bool:
    return bool(settings(name)["enabled"])


def validate(name: str, change: dict) -> str | None:
    if name not in entities.ENTITY_TYPES:
        return f"no connector named {name!r}"
    if unknown := set(change) - {"mode", "everyHours", "enabled"}:
        return f"unknown settings {sorted(unknown)}"
    if "mode" in change and change["mode"] not in MODES:
        return f"mode must be one of {', '.join(MODES)}"
    if "everyHours" in change:
        try:
            h = float(change["everyHours"])
        except (TypeError, ValueError):
            return "everyHours must be a number"
        if h < MIN_HOURS:
            return f"read at most every {MIN_HOURS * 60:.0f} minutes"
    if "enabled" in change and not isinstance(change["enabled"], bool):
        return "enabled must be true or false"
    return None


def save(name: str, change: dict) -> dict:
    """Validate and save; settings equal to the defaults are not stored, so a reset is saving the defaults."""
    if err := validate(name, change):
        raise ValueError(err)
    saved = _saved()
    merged = settings(name) | change
    if "everyHours" in merged:
        merged["everyHours"] = float(merged["everyHours"])
    diff = {k: v for k, v in merged.items() if defaults(name)[k] != v}
    if diff:
        saved[name] = diff
    else:
        saved.pop(name, None)
    paths.CONNECTORS_FILE.parent.mkdir(parents=True, exist_ok=True)
    paths.CONNECTORS_FILE.write_text(json.dumps(saved, indent=1))
    return settings(name)


def customised(name: str) -> bool:
    return name in _saved()
