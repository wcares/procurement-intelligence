"""Typed decisions from a decision model: a state plus questions with fixed options in, one probability per option out,
no generated text. Served by llama.cpp's /v1/systemone API, e.g.

    llama-server -m Laya-Q8_0.gguf --alias laya --host 127.0.0.1 --port 8082 -c 8192 -np 1

Environment:
  PROCINTEL_DECIDE_API_BASE   server root, e.g. http://127.0.0.1:8082 (the /v1/systemone path is added here)

If unset, `available()` is False and callers keep their non-model fallbacks. Questions are asked as "choice" type:
on our pre-registered check (scratch eval, 2026-10-24) choice answers were the tested path; the model's yes/no type was not.
"""
from __future__ import annotations

import json
import os
import urllib.request

YES, NO = "yes", "no"


def api_base() -> str | None:
    return os.environ.get("PROCINTEL_DECIDE_API_BASE") or None


def available() -> bool:
    return api_base() is not None


def choices(state: str, questions: dict[str, tuple[str, list[str]]], *, timeout: float = 60) -> dict[str, dict[str, float]]:
    """{question id: {option: probability}}. questions: {id: (instructions, options)}; each is answered independently."""
    base = api_base()
    if base is None:
        raise RuntimeError("PROCINTEL_DECIDE_API_BASE is not set")
    body = {"state": state, "questions": {
        qid: {"type": "choice", "instructions": text, "criteria": {o: None for o in options}}
        for qid, (text, options) in questions.items()}}
    req = urllib.request.Request(base.rstrip("/") + "/v1/systemone", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        answers = json.load(resp)["answers"]
    out = {qid: answers[qid]["probabilities"] for qid in questions}
    for qid, (_, options) in questions.items():
        if set(out[qid]) != set(options):
            raise RuntimeError(f"decision server answered {qid} with options {sorted(out[qid])}, asked {sorted(options)}")
    return out


def yes(state: str, question: str, **kw) -> float:
    """Probability of "yes" to one yes/no question, asked as a two-option choice."""
    return choices(state, {"q": (question, [YES, NO])}, **kw)["q"][YES]
