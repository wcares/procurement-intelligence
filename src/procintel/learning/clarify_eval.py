"""Does clarifying a question before searching help? Compares answers to messy wordings of labelled questions
(eval/messy_questions.jsonl: casual wording, typos, fragments; each names the labelled question it rephrases) with
CLARIFY off and on, against the same relevance labels, plus the refusal of the unanswerable questions with it on.

    python -m procintel.learning.clarify_eval        # about 30 minutes with a local 27B model; writes eval/clarify_report.md
"""
from __future__ import annotations

import json
import sys
import time

from procintel.answering import answer
from procintel.answering.retrieve import Retriever
from procintel.core import paths
from procintel.learning import evaluate

MESSY = paths.EVAL_DIR / "messy_questions.jsonl"
REPORT = paths.EVAL_DIR / "clarify_report.md"


def _scores(r: Retriever, items: list[tuple[str, str]], rel: dict[str, set[str]], clarify: int) -> dict:
    """items: (labelled question id, wording to ask). Precision and recall of the cited passages against the labels."""
    answer.CLARIFY = clarify
    n = answered = cited = hit = 0
    recall, seconds, understood = [], [], []
    for qid, text in items:
        t = time.time()
        out = answer.ask(r, text)
        seconds.append(time.time() - t)
        ids = [c["id"] for c in out["citations"]]
        n += 1
        answered += not out["unsupported"]
        cited += len(ids)
        hit += sum(i in rel[qid] for i in ids)
        recall.append(len(set(ids) & rel[qid]) / len(rel[qid]) if rel[qid] else 0.0)
        understood.append(next((c for c in out["meta"]["caveats"] if c.startswith("Understood as")), ""))
    return {"n": n, "answered": answered, "cited": cited, "precision": round(hit / cited, 3) if cited else None,
            "recall": round(sum(recall) / len(recall), 3), "median_s": round(sorted(seconds)[len(seconds) // 2], 1), "understood": understood}


def main() -> None:
    r = Retriever()
    js = evaluate._load_judgments()
    qs = {q["id"]: q for q in evaluate.questions()}
    rel = {i: {c for (qid, c), j in js.items() if qid == i and j["relevant"]} for i in qs}
    messy = [json.loads(line) for line in MESSY.read_text().splitlines() if line.strip()]
    clean = [(m["id"], qs[m["id"]]["question"]) for m in messy]
    rough = [(m["id"], m["question"]) for m in messy]
    traps = [q["question"] for q in qs.values() if not q["answerable"]]
    rows = {"clean wording, off": _scores(r, clean, rel, 0), "messy wording, off": _scores(r, rough, rel, 0),
            "messy wording, clarify on": _scores(r, rough, rel, 1)}
    answer.CLARIFY = 1
    refused = sum(answer.ask(r, t)["unsupported"] for t in traps)
    lines = ["# Clarify before searching: messy wordings", "",
             f"{len(messy)} labelled questions, each also in messy wording; the cited passages are scored against the same labels.", "",
             "| Run | Answered | Cited passages | Precision | Recall | Median seconds |", "|---|---|---|---|---|---|"]
    lines += [f"| {k} | {v['answered']}/{v['n']} | {v['cited']} | {v['precision']} | {v['recall']} | {v['median_s']} |" for k, v in rows.items()]
    lines += ["", f"Unanswerable questions refused with clarify on: {refused}/{len(traps)}.", "", "## What the model understood", ""]
    lines += [f"- {m['question']!r} -> {u or 'unchanged'}" for m, u in zip(messy, rows["messy wording, clarify on"]["understood"])]
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
