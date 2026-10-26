"""The labelling queue on the Evaluation page: the checks that keep the evaluation honest, done by a person.

    judge checks       random relevance judgments (eval/judgments.jsonl) a person confirms or corrects; agreement
                       shows how far the judge's labels, and so the search precision and recall, can be trusted
    sentence checks    answer sentences where the answer model and the independent judge disagree on whether the
                       cited passages support them (eval/faithfulness.jsonl, latest full run); a person decides
    new questions      questions the system refused or users rated not useful (feedback review) to add to the
                       evaluation set (eval/questions.jsonl), as answerable or as a trap that must be refused

A person's labels go to eval/human_labels.jsonl (kept with the evaluation files). Nothing here changes a judgment:
the labels measure the judges.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from procintel.core import db, paths
from procintel.learning import evaluate, feedback_review

HUMAN_LABELS = paths.EVAL_DIR / "human_labels.jsonl"
SAMPLE = 10


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def labels(path: Path | None = None) -> list[dict]:
    return _rows(path or HUMAN_LABELS)


def _order(key: str) -> str:
    """A fixed pseudo-random order, so the queue does not reshuffle between visits."""
    return hashlib.sha256(key.encode()).hexdigest()


def _passages(ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    con = db.connect(read_only=True)
    try:
        return dict(con.execute("SELECT chunk_id, text FROM chunk WHERE chunk_id IN (SELECT unnest(?))", [ids]).fetchall())
    finally:
        con.close()


def judge_checks(n: int = SAMPLE) -> dict:
    done = {(r["qid"], r["chunk_id"]) for r in labels() if r["kind"] == "judge"}
    qs = {q["id"]: q["question"] for q in evaluate.questions()}
    todo = sorted((j for k, j in evaluate._load_judgments().items() if k not in done and j["qid"] in qs),
                  key=lambda j: _order(j["qid"] + j["chunk_id"]))[:n]
    text = _passages([j["chunk_id"] for j in todo])
    mine = [r for r in labels() if r["kind"] == "judge"]
    return {"items": [{"qid": j["qid"], "question": qs[j["qid"]], "chunkId": j["chunk_id"], "passage": text.get(j["chunk_id"]),
                       "judge": j["relevant"], "judgeModel": j.get("judge")} for j in todo],
            "agreement": {"agree": sum(r["human"] == r["judge"] for r in mine), "labelled": len(mine)}}


def _sentence_key(v: dict) -> str:
    return v["qid"] + "|" + v["sentence"]


def sentence_checks() -> dict:
    done = {r["key"] for r in labels() if r["kind"] == "sentence"}
    rows = _rows(evaluate.FAITHFULNESS)
    split = [v for v in rows if v.get("independent") is not None and v["answer_llm"] != v["independent"]]
    mine = [r for r in labels() if r["kind"] == "sentence"]
    return {"items": [{"key": _sentence_key(v), "qid": v["qid"], "sentence": v["sentence"], "passages": v["passages"],
                       "answerModel": v["answer_llm"], "independent": v["independent"]}
                      for v in split if _sentence_key(v) not in done],
            "sentences": len(rows), "disagreements": len(split),
            "decided": {"answerModel": sum(r["human"] == r["answer_model"] for r in mine),
                        "independent": sum(r["human"] == r["independent"] for r in mine), "labelled": len(mine)}}


def question_candidates() -> list[dict]:
    have = {q["question"].lower().strip() for q in evaluate.questions()}
    out = []
    for it in feedback_review.items(limit=100):
        if it["kind"] not in ("refused_question", "not_useful"):
            continue
        q = it["questions"][0] if it["questions"] else it["key"]
        out.append({"kind": it["kind"], "question": q, "responses": it["responses"], "comments": it["comments"],
                    "inSet": q.lower().strip() in have})
    return out


def queue() -> dict:
    return {"judge": judge_checks(), "sentences": sentence_checks(), "questions": question_candidates()}


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def label_judgment(qid: str, chunk_id: str, relevant: bool, by: str | None) -> dict:
    j = evaluate._load_judgments().get((qid, chunk_id))
    if j is None:
        raise KeyError("no such judgment")
    row = {"kind": "judge", "qid": qid, "chunk_id": chunk_id, "judge": j["relevant"], "human": relevant,
           "judge_model": j.get("judge"), "by": by, "at": _now()}
    _append(HUMAN_LABELS, row)
    return row


def label_sentence(key: str, supported: bool, by: str | None) -> dict:
    v = next((v for v in _rows(evaluate.FAITHFULNESS) if _sentence_key(v) == key), None)
    if v is None:
        raise KeyError("no such sentence in the latest run")
    row = {"kind": "sentence", "key": key, "qid": v["qid"], "answer_model": v["answer_llm"],
           "independent": v["independent"], "human": supported, "by": by, "at": _now()}
    _append(HUMAN_LABELS, row)
    return row


def add_question(question: str, answerable: bool, note: str | None) -> dict:
    """Append to the evaluation set with the next free id; an answerable one is judged on the next evaluation run."""
    question = question.strip()
    qs = evaluate.questions()
    if not question:
        raise ValueError("the question is empty")
    if question.lower() in {q["question"].lower().strip() for q in qs}:
        raise ValueError("this question is already in the evaluation set")
    n = max((int(q["id"][1:]) for q in qs if q["id"][1:].isdigit()), default=0) + 1
    row = {"id": f"q{n:02d}", "question": question, "answerable": answerable,
           "note": note or "added from user feedback on the Evaluation page"}
    _append(evaluate.QUESTIONS, row)
    return row
