"""Prompts as versioned text, editable on the Settings page instead of in code.

Every prompt the code sends to a model has a name here (PROMPTS). Its default is src/procintel/prompts/<name>.txt;
edits are saved as numbered versions in the data folder (prompts/<name>/v<N>.txt, procintel.core.paths) with the
active version in prompts/<name>/active (0 = the default). A new version is saved as a candidate: prompts used in
answering are evaluated first (procintel.learning.prompt_eval: the active and the candidate version answer the same
questions) and then activated; the others are activated directly, since nothing measures them automatically.

Prompts are read on every call, so an activation applies to the next request in every process sharing the data
folder. Values are filled in with ${name} placeholders (string.Template), so JSON braces in a prompt need no escaping.
An evaluation runs with override(), which changes the prompt only for the code running inside it.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from string import Template

from procintel.core import paths

DEFAULTS = Path(str(resources.files("procintel") / "prompts"))  # default texts, shipped with the code


@dataclass(frozen=True)
class Prompt:
    name: str
    label: str
    used_by: str
    evaluated_by: str | None  # "answers": the prompt evaluation can compare versions; None: activated directly


PROMPTS = {p.name: p for p in [
    Prompt("answer", "Answer writer", "Ask: writes the cited sentences (procintel.answering.answer)", "answers"),
    Prompt("evidence_gate", "Evidence check", "Ask: keeps only passages that help answer the question", "answers"),
    Prompt("rephrase", "Question rephrasing", "Ask: search queries in the reports' words", "answers"),
    Prompt("precedents", "Precedent picker", "Assess: picks past lessons for the planned package", None),
    Prompt("problem_check", "Problem check", "Passage tags step 1: does the passage describe a problem", None),
    Prompt("problem_kind", "Problem kind", "Passage tags step 2: which kind (${kinds} = the fixed list)", None),
    Prompt("judge_relevance", "Judge: relevance", "Evaluation: labels search results relevant or not", None),
    Prompt("judge_support", "Judge: support", "Evaluation: checks answer sentences against their passages", None),
]}

_overrides: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar("prompt_overrides", default={})


def _dir(name: str) -> Path:
    return paths.DATA_DIR / "prompts" / name


def _read(path: Path) -> str:
    return path.read_text().removesuffix("\n")


def active_version(name: str) -> int:
    f = _dir(name) / "active"
    return int(f.read_text().strip()) if f.exists() else 0


def text(name: str, version: int | None = None) -> str:
    """The raw text of a version (None: the active one; 0: the default file)."""
    if name not in PROMPTS:
        raise KeyError(f"unknown prompt {name!r}")
    v = active_version(name) if version is None else version
    return _read(DEFAULTS / f"{name}.txt") if v == 0 else _read(_dir(name) / f"v{v}.txt")


def get(name: str, **values: str) -> str:
    """The prompt to send: an override set by an evaluation, else the active version, with ${placeholders} filled."""
    raw = _overrides.get().get(name) or text(name)
    return Template(raw).safe_substitute(values) if values else raw


@contextlib.contextmanager
def override(name: str, version: int):
    """Use another version of one prompt for the code running inside the block (other threads are not affected)."""
    token = _overrides.set(_overrides.get() | {name: text(name, version)})
    try:
        yield
    finally:
        _overrides.reset(token)


def _meta_file(name: str) -> Path:
    return _dir(name) / "versions.json"


def _meta(name: str) -> dict:
    f = _meta_file(name)
    return json.loads(f.read_text()) if f.exists() else {}


def _set_meta(name: str, version: int, **fields) -> None:
    meta = _meta(name)
    meta.setdefault(str(version), {}).update(fields)
    _dir(name).mkdir(parents=True, exist_ok=True)
    _meta_file(name).write_text(json.dumps(meta, indent=1))


def save(name: str, new_text: str, note: str = "") -> int:
    """Store a new version (not active yet); returns its number."""
    if name not in PROMPTS:
        raise KeyError(f"unknown prompt {name!r}")
    if not new_text.strip():
        raise ValueError("a prompt cannot be empty")
    d = _dir(name)
    d.mkdir(parents=True, exist_ok=True)
    v = max([int(p.stem[1:]) for p in d.glob("v*.txt")] + [0]) + 1
    (d / f"v{v}.txt").write_text(new_text.rstrip("\n") + "\n")
    _set_meta(name, v, created=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), note=note)
    return v


def activate(name: str, version: int) -> None:
    text(name, version)  # raises when the version does not exist
    _dir(name).mkdir(parents=True, exist_ok=True)
    (_dir(name) / "active").write_text(f"{version}\n")
    _set_meta(name, version, activated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))


def record_evaluation(name: str, version: int, result: dict) -> None:
    _set_meta(name, version, evaluation=result)


def listing() -> list[dict]:
    out = []
    for p in PROMPTS.values():
        meta, active = _meta(p.name), active_version(p.name)
        nums = sorted([0] + [int(f.stem[1:]) for f in _dir(p.name).glob("v*.txt")])
        out.append({"name": p.name, "label": p.label, "usedBy": p.used_by, "evaluatedBy": p.evaluated_by,
                    "active": active,
                    "versions": [{"version": v, "text": text(p.name, v), "active": v == active,
                                  **{k: meta.get(str(v), {}).get(k) for k in ("created", "note", "activated", "evaluation")}}
                                 for v in nums]})
    return out
