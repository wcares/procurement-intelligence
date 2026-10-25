"""Evaluation of retrieval and answers on a small labelled question set (eval/questions.jsonl).

Relevance labels: for each answerable question, the top 10 passages of keyword-only (BM25) search and the top 10 of
hybrid search are pooled, and a judge model labels each pooled passage relevant or not. The judge is the answer LLM
(procintel.llm), not the decision model the pipeline uses as its evidence gate, so the gate is not graded by itself.
Judgments are cached in eval/judgments.jsonl; a hand-checked sample gives the judge's agreement with a person.

Recall is measured against the pooled relevant set, so it is an upper bound: a relevant passage neither search found
is not counted as missed.

    python -m procintel.evaluate judge    # pool candidates and judge any not yet judged
    python -m procintel.evaluate sample   # print 30 random judgments for a hand check
    python -m procintel.evaluate run      # metrics, written to eval/report.md
"""
from __future__ import annotations

import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from procintel import answer, decide, embed, llm
from procintel.retrieve import Retriever

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "eval" / "questions.jsonl"
JUDGMENTS = ROOT / "eval" / "judgments.jsonl"
REPORT = ROOT / "eval" / "report.md"
POOL_K = 10

_REL = ("You judge search results for procurement planners. Reply with one word, yes or no: does the passage contain "
        "information that helps answer the question?")
_SUP = ("You check statements against sources. Reply with one word, yes or no: is every fact in the statement "
        "supported by the passages? Paraphrase is fine; facts missing from the passages are not.")


def questions() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]


def _yes(system: str, user: str) -> bool:
    out = llm.complete(system, user, max_tokens=4).strip().lower()
    if not out.startswith(("yes", "no")):
        raise RuntimeError(f"judge replied {out!r}, expected yes or no")
    return out.startswith("yes")


def _load_judgments() -> dict[tuple[str, str], dict]:
    if not JUDGMENTS.exists():
        return {}
    return {(j["qid"], j["chunk_id"]): j for j in map(json.loads, JUDGMENTS.read_text().splitlines()) if j}


def _search(r: Retriever, q: str, k: int, hybrid: bool) -> list:
    vectors = r.vectors
    if not hybrid:
        r.vectors = None
    try:
        return r.search(q, k=k)
    finally:
        r.vectors = vectors


def judge(r: Retriever) -> None:
    if not llm.available():
        raise SystemExit("set PROCINTEL_LLM_MODEL for the judge")
    done = _load_judgments()
    todo = []
    for q in questions():
        if not q["answerable"]:
            continue
        pool = {h.chunk_id: h for h in _search(r, q["question"], POOL_K, False) + _search(r, q["question"], POOL_K, True)}
        todo += [(q, h) for cid, h in pool.items() if (q["id"], cid) not in done]
    print(f"judging {len(todo)} new (question, passage) pairs with {llm.model_name()}; {len(done)} cached")
    t0 = time.time()
    with JUDGMENTS.open("a") as f:
        for i, (q, h) in enumerate(todo, 1):
            rel = _yes(_REL, f"Question: {q['question']}\n\nPassage: {h.text}")
            f.write(json.dumps({"qid": q["id"], "chunk_id": h.chunk_id, "relevant": rel, "judge": llm.model_name()}) + "\n")
            f.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
    print(f"done in {time.time() - t0:.0f}s")


def sample(r: Retriever, n: int = 30, seed: int = 7) -> None:
    js = list(_load_judgments().values())
    qs = {q["id"]: q["question"] for q in questions()}
    text = {rec["chunk_id"]: rec["text"] for rec in r.records}
    for j in random.Random(seed).sample(js, min(n, len(js))):
        print(f"[{j['qid']}|{'REL' if j['relevant'] else 'not'}] {j['chunk_id']}  Q: {qs[j['qid']]}\n    {text.get(j['chunk_id'], '?')[:600]}\n")


def run(r: Retriever) -> str:
    js = _load_judgments()
    qs = questions()
    rel = {q["id"]: {c for (qid, c), j in js.items() if qid == q["id"] and j["relevant"]} for q in qs if q["answerable"]}
    rows, totals = [], {}
    for q in qs:
        if not q["answerable"]:
            continue
        R = rel[q["id"]]
        bm = [h.chunk_id for h in _search(r, q["question"], POOL_K, False)]
        hy = [h.chunk_id for h in _search(r, q["question"], 12, True)]
        gated, how = answer.supporting(q["question"], _search(r, q["question"], 12, True))
        gate = [h.chunk_id for h in gated]
        unjudged = [c for c in set(bm[:5] + hy[:5] + gate) if (q["id"], c) not in js]
        m = {"bm25_p5": _prec(bm[:5], R), "hybrid_p5": _prec(hy[:5], R), "bm25_r10": _rec(bm[:10], R),
             "hybrid_r10": _rec(hy[:10], R), "gate_prec": _prec(gate, R), "gate_n": len(gate)}
        rows.append((q, len(R), m, how, unjudged))
        for k, v in m.items():
            if v is not None:
                totals.setdefault(k, []).append(v)
    ans = []
    for q in qs:
        t = time.time()
        out = answer.ask(r, q["question"])
        cites = out["citations"]
        sup = [_yes(_SUP, "Passages:\n" + "\n\n".join(cites[c]["quote"] for c in s["citations"]) + f"\n\nStatement: {s['text']}")
               for s in out["answer"]]
        ans.append((q, out["unsupported"], len(sup), sum(sup), time.time() - t))
    return _report(rows, totals, ans, len(js))


def _prec(ids: list[str], rel: set[str]) -> float | None:
    return sum(c in rel for c in ids) / len(ids) if ids else None


def _rec(ids: list[str], rel: set[str]) -> float | None:
    return sum(c in rel for c in ids) / len(rel) if rel else None


def _report(rows, totals, ans, n_judged) -> str:
    mean = lambda k: sum(totals[k]) / len(totals[k]) if totals.get(k) else float("nan")  # noqa: E731
    answerable = [a for a in ans if a[0]["answerable"]]
    traps = [a for a in ans if not a[0]["answerable"]]
    n_sent = sum(a[2] for a in answerable)
    n_sup = sum(a[3] for a in answerable)
    lines = [
        f"# Evaluation report ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})",
        "",
        f"Models: answers and judge `{llm.model_name()}`; embeddings `{embed.model_name()}`; decision `{decide.api_base()}`.",
        f"{len(rows)} answerable questions, {len(traps)} unanswerable; {n_judged} judged (question, passage) pairs.",
        "Recall is against the pooled relevant set (BM25 top 10 + hybrid top 10), so it is an upper bound.",
        "Relevance judge vs a hand check of 30 judgments: 28/30 agree, both misses lenient (eval/judge_check.md).",
        "Faithfulness is judged by the same model that writes the answers, which may favour its own sentences.",
        "",
        "## Retrieval",
        "",
        "| metric | value |",
        "|---|---|",
        f"| BM25 precision@5 | {mean('bm25_p5'):.2f} |",
        f"| Hybrid precision@5 | {mean('hybrid_p5'):.2f} |",
        f"| BM25 recall@10 | {mean('bm25_r10'):.2f} |",
        f"| Hybrid recall@10 | {mean('hybrid_r10'):.2f} |",
        f"| Evidence gate precision (passages kept as evidence) | {mean('gate_prec'):.2f} |",
        "",
        "## Answers",
        "",
        "| metric | value |",
        "|---|---|",
        f"| Answerable questions answered (not refused) | {sum(not a[1] for a in answerable)}/{len(answerable)} |",
        f"| Answer sentences supported by their citations (judge) | {n_sup}/{n_sent} ({n_sup / n_sent:.0%}) |" if n_sent else "| Answer sentences | 0 |",
        f"| Unanswerable questions refused | {sum(a[1] for a in traps)}/{len(traps)} |",
        f"| Median time per question | {sorted(a[4] for a in ans)[len(ans) // 2]:.1f} s |",
        "",
        "## Per question",
        "",
        "| id | question | relevant in pool | BM25 P@5 | hybrid P@5 | gate kept / precision | answer |",
        "|---|---|---|---|---|---|---|",
    ]
    by_q = {a[0]["id"]: a for a in ans}
    f = lambda v: "–" if v is None else f"{v:.2f}"  # noqa: E731
    for q, n_rel, m, how, unjudged in rows:
        a = by_q[q["id"]]
        res = "refused" if a[1] else f"{a[3]}/{a[2]} supported"
        lines.append(f"| {q['id']} | {q['question']} | {n_rel} | {f(m['bm25_p5'])} | {f(m['hybrid_p5'])} | "
                     f"{m['gate_n']} / {f(m['gate_prec'])}{' (unjudged: ' + str(len(unjudged)) + ')' if unjudged else ''} | {res} |")
    for q, unsupported, n, k, _ in traps:
        lines.append(f"| {q['id']} | {q['question']} | – | – | – | – | {'refused' if unsupported else f'ANSWERED ({k}/{n} supported)'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    r = Retriever()
    if cmd == "judge":
        judge(r)
    elif cmd == "sample":
        sample(r)
    else:
        report = run(r)
        REPORT.write_text(report)
        print(report)


if __name__ == "__main__":
    main()
