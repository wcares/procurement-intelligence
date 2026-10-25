"""Compare two versions of an answering prompt before one is activated (procintel.core.prompts).

The active and the candidate version answer the same fixed sample of evaluation questions (SAMPLE_ANSWERABLE
answerable ones and SAMPLE_TRAPS that the reports cannot answer), one question per job step so the job pauses when
the app is used. For each version: questions answered, answer sentences the answer model's judge finds supported by
their passages, traps refused, median seconds. Nothing is written to the main evaluation report.
"""
from __future__ import annotations

import time
from typing import Iterator

from procintel.core import llm, prompts
from procintel.learning import evaluate

SAMPLE_ANSWERABLE = 15
SAMPLE_TRAPS = 5
_retriever = None


def sample() -> list[dict]:
    qs = evaluate.questions()
    return [q for q in qs if q["answerable"]][:SAMPLE_ANSWERABLE] + [q for q in qs if not q["answerable"]][:SAMPLE_TRAPS]


def _search_index():
    global _retriever
    if _retriever is None:  # built once per process; a job resumed later reuses it
        from procintel.answering.retrieve import Retriever
        _retriever = Retriever()
    return _retriever


def _one(q: dict) -> dict:
    from procintel.answering import answer
    t = time.time()
    out = answer.ask(_search_index(), q["question"])
    secs = time.time() - t
    cites, supported = out["citations"], 0
    for s in out["answer"]:
        passages = "\n\n".join(cites[c]["quote"] for c in s["citations"])
        reply = llm.complete(prompts.get("judge_support"), f"Passages:\n{passages}\n\nStatement: {s['text']}", max_tokens=4)
        supported += reply.strip().lower().startswith("yes")
    return {"answerable": q["answerable"], "answered": not out["unsupported"], "sentences": len(out["answer"]),
            "supported": supported, "seconds": round(secs, 1)}


def summarise(rows: list[dict]) -> dict:
    ans = [r for r in rows if r["answerable"]]
    traps = [r for r in rows if not r["answerable"]]
    secs = sorted(r["seconds"] for r in rows)
    return {"answered": sum(r["answered"] for r in ans), "answerable": len(ans),
            "supported_sentences": sum(r["supported"] for r in ans), "sentences": sum(r["sentences"] for r in ans),
            "refused_traps": sum(not r["answered"] for r in traps), "traps": len(traps),
            "median_seconds": secs[len(secs) // 2] if secs else None}


def steps(name: str, candidate: int, cursor: dict | None) -> Iterator[dict]:
    """Job steps: one question answered with both versions per step; the cursor carries the rows so far."""
    cur = cursor or {"i": 0, "active": [], "candidate": [], "active_version": prompts.active_version(name)}
    qs = sample()
    for i in range(cur["i"], len(qs)):
        with prompts.override(name, cur["active_version"]):
            cur["active"].append(_one(qs[i]))
        with prompts.override(name, candidate):
            cur["candidate"].append(_one(qs[i]))
        cur["i"] = i + 1
        yield cur
    result = {"versions": {"active": cur["active_version"], "candidate": candidate}, "questions": len(qs),
              "active": summarise(cur["active"]), "candidate": summarise(cur["candidate"])}
    prompts.record_evaluation(name, candidate, result)
    return result
