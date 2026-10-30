"""Runtime settings the configuration page can view and change.

Each setting is either an environment variable that the code reads on every call (model names, endpoints) or a module
constant read on every call (thresholds, retrieval sizes), so a change applies to the next request without a restart.
Settings that cannot change safely at runtime are listed read-only with the steps they need: the embedding model and
dimensions must match the stored passage vectors, so changing them means `python -m procintel.core.embed` and a restart.

API keys are never listed or editable here. Saved overrides live in data/config.json and are applied at startup.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from procintel.answering import answer, retrieve
from procintel.core import embed, llm, paths
from procintel.ingestion import chunk
from procintel.jobs import handlers, retention, worker as jobs_worker
from procintel.learning import feedback_review
from procintel.prediction import assess

SAVED = paths.CONFIG_FILE
PROFILES = paths.PROFILES_FILE  # named sets of settings


@dataclass
class Setting:
    key: str
    label: str
    group: str
    type: str  # "str" | "url" | "json" | "int" | "float" | "date"
    get: Callable[[], Any]
    set: Callable[[Any], None] | None  # None: read-only
    note: str
    min: float | None = None
    max: float | None = None
    default: Any = field(default=None)


def _env(name: str) -> tuple[Callable[[], Any], Callable[[Any], None]]:
    def put(v):
        if v in (None, ""):
            os.environ.pop(name, None)
        else:
            os.environ[name] = v
    return (lambda: os.environ.get(name) or ""), put


def _attr(module, name: str) -> tuple[Callable[[], Any], Callable[[Any], None]]:
    return (lambda: getattr(module, name)), (lambda v: setattr(module, name, v))


def _settings() -> list[Setting]:
    out = [
        Setting("llm_model", "Answer model", "Models", "str", *_env("PROCINTEL_LLM_MODEL"),
                "LiteLLM model string, e.g. openai/saluki-27b. Empty: answers are quoted sentences."),
        Setting("llm_api_base", "Answer model endpoint", "Models", "url", *_env("PROCINTEL_LLM_API_BASE"),
                "OpenAI-compatible endpoint, e.g. http://127.0.0.1:8080/v1"),
        Setting("llm_extra_body", "Answer model extra options", "Models", "json", *_env("PROCINTEL_LLM_EXTRA_BODY"),
                'JSON merged into each request, e.g. {"chat_template_kwargs": {"enable_thinking": false}}'),
        Setting("llm_temperature", "Answer temperature", "Models", "float", *_attr(llm, "TEMPERATURE"),
                "0 = deterministic", 0, 2),
        Setting("llm_max_tokens", "Answer max tokens", "Models", "int", *_attr(llm, "MAX_TOKENS"),
                "A reply cut at this limit is treated as a failure, not an answer", 64, 8192),
        Setting("judge_model", "Independent judge model", "Models", "str", *_env("PROCINTEL_JUDGE_MODEL"),
                "Evaluation only: a second model that checks answer sentences, e.g. openai/qwen3-vl-8b. Empty: the "
                "answer model is the only judge."),
        Setting("judge_api_base", "Independent judge endpoint", "Models", "url", *_env("PROCINTEL_JUDGE_API_BASE"),
                "OpenAI-compatible endpoint of the judge model"),
        Setting("judge_extra_body", "Independent judge extra options", "Models", "json", *_env("PROCINTEL_JUDGE_EXTRA_BODY"),
                "JSON merged into each judge request"),
        Setting("batch_model", "Background jobs model", "Models", "str", *_env("PROCINTEL_BATCH_MODEL"),
                "The model for tagging passages, evaluations and prompt tests (LiteLLM string). Empty: the answer model, "
                "and jobs that use it wait for quiet. Another model or endpoint: those jobs run at any time, so users are never slowed"),
        Setting("batch_api_base", "Background jobs endpoint", "Models", "url", *_env("PROCINTEL_BATCH_API_BASE"),
                "OpenAI-compatible endpoint of that model. Empty: the answer model's. The API key is PROCINTEL_BATCH_API_KEY in .env"),
        Setting("batch_extra_body", "Background jobs extra options", "Models", "json", *_env("PROCINTEL_BATCH_EXTRA_BODY"),
                "JSON merged into the request body for that model. Empty: the answer model's, if it is the same model"),
        Setting("decide_api_base", "Decision model endpoint", "Models", "url", *_env("PROCINTEL_DECIDE_API_BASE"),
                "llama-server with /v1/systemone. Empty: evidence and support are checked by word overlap."),
        Setting("embed_model", "Embedding model", "Models", "str", lambda: embed.model_name() or "", None,
                "Read-only here: stored passage vectors belong to one model. Change it in .env, run "
                "`python -m procintel.core.embed`, restart the backend."),
        Setting("embed_dim", "Embedding dimensions", "Models", "int", embed.dim, None,
                "Read-only here, for the same reason as the embedding model."),
        Setting("search_k", "Passages retrieved per question", "Retrieval", "int", *_attr(answer, "SEARCH_K"),
                "Candidates before the evidence check", 1, 50),
        Setting("pool", "Candidates per ranking before fusion", "Retrieval", "int", *_attr(retrieve, "POOL"),
                "Taken from BM25 and from vector search, then merged", 5, 500),
        Setting("rrf_k", "Rank fusion constant", "Retrieval", "int", *_attr(retrieve, "RRF_K"),
                "Higher values flatten the difference between top and lower ranks (60 is the usual choice)", 1, 1000),
        Setting("min_evidence", "Second-search trigger", "Retrieval", "int", *_attr(answer, "MIN_EVIDENCE"),
                "With fewer evidence passages than this, the question is rephrased by the answer model and searched "
                "again (0 = never)", 0, 12),
        Setting("max_passages", "Evidence passages per answer", "Evidence", "int", *_attr(answer, "MAX_PASSAGES"),
                "Passages kept as evidence and shown to the answer model", 1, 12),
        Setting("clarify", "Clarify questions before searching", "Retrieval", "int", *_attr(answer, "CLARIFY"),
                "1: the answer model first rewrites a casual or unclear question as a clear one (~2 s) and the rest of "
                "the answer works from that; 0: the question as typed", 0, 1),
        Setting("vocab_step", "Rephrase questions in the reports' words", "Retrieval", "int", *_attr(answer, "VOCAB_STEP"),
                "1: the answer model rephrases each question in the reports' vocabulary and both are searched (~2 s); "
                "0: the question only, rephrased just when evidence is thin", 0, 1),
        Setting("llm_gate", "Evidence judged by the answer model", "Evidence", "int", *_attr(answer, "LLM_GATE"),
                "1: the answer model picks the evidence passages in one call (more precise, ~14 s); 0: the decision "
                "model judges each passage (~0.4 s)", 0, 1),
        Setting("decide_min", "Decision threshold", "Evidence", "float", *_attr(answer, "DECIDE_MIN"),
                "Probability needed for 'relevant' and 'supported' (decision model)", 0.05, 0.99),
        Setting("grounding_min", "Word-overlap threshold", "Evidence", "float", *_attr(answer, "GROUNDING_MIN"),
                "Fallback without a decision model: share of a sentence's words that must be in its citation", 0, 1),
        Setting("jobs_idle_seconds", "Idle time before background jobs run", "Background jobs", "int",
                *_attr(jobs_worker, "IDLE_SECONDS"),
                "Seconds without any request before the queue (drift check, retraining) starts; a request pauses it",
                10, 86400),
        Setting("jobs_max_wait_seconds", "Longest a job waits for quiet", "Background jobs", "int",
                *_attr(jobs_worker, "MAX_WAIT_SECONDS"),
                "With users active all day, quiet never comes: a job that has waited this long runs anyway (background "
                "jobs, such as evaluations, wait 12 times as long). Jobs that do not use the models (change detection, "
                "drift check, retention, retraining) never wait for quiet", 60, 604800),
        Setting("demote_min", "Flags before a citation is demoted", "Background jobs", "int",
                *_attr(feedback_review, "DEMOTE_MIN"),
                "Separate responses that must flag a passage as a wrong citation before search moves it to the end "
                "of its results (applied by the next feedback review job)", 1, 100),
        Setting("not_a_lesson_min", "Precedent filter threshold", "Assess", "float", *_attr(assess, "NOT_A_LESSON_MIN"),
                "Tag confidence above which a 'no problem' passage is not shown as a precedent (1 = never filter)", 0.5, 1),
        Setting("drift_min_new", "Drift check: minimum new packages", "Background jobs", "int",
                *_attr(handlers, "MIN_NEW"), "Fewer packages labelled since training than this: too few to judge the "
                "model on", 1, 10000),
        Setting("drift_growth", "Drift check: retrain on growth", "Background jobs", "float",
                *_attr(handlers, "GROWTH"), "Retrain when the newly labelled packages reach this share of the "
                "training set", 0.0, 1.0),
        Setting("drift_error_ratio", "Drift check: error ratio", "Background jobs", "float",
                *_attr(handlers, "ERROR_RATIO"), "Retrain when the error on new packages exceeds the cross-validated "
                "error by this factor", 1.0, 10.0),
        Setting("retention_days", "Keep logs and history (days)", "Background jobs", "int", *_attr(retention, "RETENTION_DAYS"),
                "Event history, finished jobs, cached API responses, refresh logs, unpromoted shadow builds and the "
                "response log and feedback older than this are deleted by the daily retention job", 1, 3650),
        Setting("pilot_until", "Pilot runs until (YYYY-MM-DD)", "Background jobs", "date", *_attr(retention, "PILOT_UNTIL"),
                "While a pilot runs, the response log and feedback are kept whole (its KPIs span its length); empty: "
                "no pilot"),
        Setting("chunk_max_chars", "Passage size limit (characters)", "Index", "int", *_attr(chunk, "MAX_CHARS"),
                "Longer paragraphs are split; applies at the next refresh (the passages are rebuilt and re-embedded)",
                300, 4000),
        Setting("flat_numbers", "Flattened table: share of numbers", "Index", "float", *_attr(chunk, "FLAT_NUMBERS"),
                "A passage with at least this share of number tokens is treated as a table and left out of search; "
                "applies at the next refresh", 0.05, 1.0),
        Setting("flat_numbers_no_sentence", "Flattened table: share without sentences", "Index", "float",
                *_attr(chunk, "FLAT_NUMBERS_NO_SENTENCE"), "The same with almost no sentence boundary; applies at the "
                "next refresh", 0.05, 1.0),
        Setting("caption_numbers", "Captioned table: share of numbers", "Index", "float",
                *_attr(chunk, "CAPTION_NUMBERS"), "A passage starting with a table caption and at least this share of "
                "numbers is a table; applies at the next refresh", 0.0, 1.0),
    ]
    return out


_DEFAULTS = {s.key: s.get() for s in _settings()}


def _coerce(s: Setting, v: Any) -> Any:
    if s.type == "int":
        if isinstance(v, bool) or not isinstance(v, (int, float, str)):
            raise ValueError("expected a whole number")
        v = int(str(v).strip())
    elif s.type == "float":
        if isinstance(v, bool) or not isinstance(v, (int, float, str)):
            raise ValueError("expected a number")
        v = float(str(v).strip())
    else:
        v = "" if v is None else str(v).strip()
        if s.type == "url" and v and not v.startswith(("http://", "https://")):
            raise ValueError("expected an http:// or https:// URL")
        if s.type == "json" and v:
            json.loads(v)  # raises ValueError on bad JSON
        if s.type == "date" and v:
            date.fromisoformat(v)  # raises ValueError unless YYYY-MM-DD
    if s.min is not None and v < s.min or s.max is not None and v > s.max:
        raise ValueError(f"must be between {s.min:g} and {s.max:g}")
    return v


def listing() -> list[dict]:
    return [{"key": s.key, "label": s.label, "group": s.group, "type": s.type, "value": s.get(),
             "default": _DEFAULTS[s.key], "editable": s.set is not None, "note": s.note, "min": s.min, "max": s.max}
            for s in _settings()]


def update(values: dict[str, Any], save: bool = False) -> dict[str, str]:
    """Validate every value first, then apply all (nothing applied if any fails). Returns {key: error} on failure."""
    by_key = {s.key: s for s in _settings()}
    errors, ready = {}, {}
    for k, v in values.items():
        s = by_key.get(k)
        if s is None:
            errors[k] = "unknown setting"
        elif s.set is None:
            errors[k] = "read-only here"
        else:
            try:
                ready[k] = _coerce(s, v)
            except (ValueError, TypeError) as e:
                errors[k] = str(e) or "invalid value"
    if errors:
        return errors
    for k, v in ready.items():
        by_key[k].set(v)
    if save:
        current = {s.key: s.get() for s in _settings() if s.set is not None and s.get() != _DEFAULTS[s.key]}
        SAVED.parent.mkdir(parents=True, exist_ok=True)
        SAVED.write_text(json.dumps(current, indent=1))
    return {}


def load_saved() -> dict[str, str]:
    """Apply data/config.json if present; returns errors for entries that no longer validate (those are skipped)."""
    if not SAVED.exists():
        return {}
    saved = json.loads(SAVED.read_text())
    errors = {}
    for k, v in saved.items():
        e = update({k: v})
        errors |= e
    return errors


def _read_profiles() -> dict[str, dict]:
    return json.loads(PROFILES.read_text()) if PROFILES.exists() else {}


def profiles() -> list[dict]:
    """Saved profiles with the settings each changes from the defaults."""
    return [{"name": n, "values": v, "differs": {k: x for k, x in v.items() if k in _DEFAULTS and x != _DEFAULTS[k]}}
            for n, v in sorted(_read_profiles().items())]


def save_profile(name: str) -> None:
    """Store every editable setting's current value under name (overwrites a profile of the same name)."""
    name = name.strip()
    if not name or len(name) > 60:
        raise ValueError("a profile name of 1 to 60 characters is needed")
    all_ = _read_profiles()
    all_[name] = {s.key: s.get() for s in _settings() if s.set is not None}
    PROFILES.parent.mkdir(parents=True, exist_ok=True)
    PROFILES.write_text(json.dumps(all_, indent=1))


def apply_profile(name: str, save: bool = False) -> dict[str, str]:
    """Apply a saved profile (all or nothing, like update); errors per key, or {"name": ...} if unknown."""
    all_ = _read_profiles()
    if name not in all_:
        return {"name": "no profile with this name"}
    known = {s.key for s in _settings() if s.set is not None}
    return update({k: v for k, v in all_[name].items() if k in known}, save=save)  # settings removed since are skipped


def delete_profile(name: str) -> bool:
    all_ = _read_profiles()
    if all_.pop(name, None) is None:
        return False
    PROFILES.write_text(json.dumps(all_, indent=1))
    return True


def compare(values: dict[str, Any], measure: Callable[[], dict]) -> dict:
    """measure() under the current settings and under values, then restore: {"before", "after"} or {"errors"}.
    Settings are module-wide, so a request served during the second measurement sees the candidate values."""
    previous = {s.key: s.get() for s in _settings() if s.set is not None}
    before = measure()
    errors = update(values)
    if errors:
        return {"errors": errors}
    try:
        after = measure()
    finally:
        update({k: previous[k] for k in values if k in previous})
    return {"before": before, "after": after}
