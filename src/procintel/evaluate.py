"""Evaluation of retrieval and answers on a small labelled question set (eval/questions.jsonl).

Relevance labels: for each answerable question, the top 10 passages of keyword-only (BM25) search and the top 10 of
hybrid search are pooled, and a judge model labels each pooled passage relevant or not. The judge is the answer LLM
(procintel.llm), not the decision model the pipeline uses as its evidence gate, so the gate is not graded by itself.
Judgments are cached in eval/judgments.jsonl; a hand-checked sample gives the judge's agreement with a person.

Recall is measured against the pooled relevant set, so it is an upper bound: a relevant passage neither search found
is not counted as missed.

Faithfulness: every answer sentence is checked against the passages it cites by the answer LLM and, when
PROCINTEL_JUDGE_MODEL is set, by an independent judge model, since a model may favour its own sentences. Both verdicts
per sentence are written to eval/faithfulness.jsonl for a hand check of the disagreements.

    python -m procintel.evaluate judge    # pool candidates and judge any not yet judged
    python -m procintel.evaluate sample   # print 30 random judgments for a hand check
    python -m procintel.evaluate run      # metrics + user feedback, written to eval/report.md, appended to eval/history.jsonl
    python -m procintel.evaluate run --no-answers   # retrieval + feedback only (what refresh runs; answers take ~10 min)
"""
from __future__ import annotations

import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from procintel import answer, decide, embed, feedback, llm
from procintel.retrieve import Retriever

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "eval" / "questions.jsonl"
JUDGMENTS = ROOT / "eval" / "judgments.jsonl"
REPORT = ROOT / "eval" / "report.md"
HISTORY = ROOT / "eval" / "history.jsonl"  # one line of headline metrics per run
FAITHFULNESS = ROOT / "eval" / "faithfulness.jsonl"  # per answer sentence: both judges' verdicts (latest run)
POOL_K = 10

_REL = ("You judge search results for procurement planners. Reply with one word, yes or no: does the passage contain "
        "information that helps answer the question?")
_SUP = ("You check statements against sources. Reply with one word, yes or no: is every fact in the statement "
        "supported by the passages? Paraphrase is fine; facts missing from the passages are not.")


def questions() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.read_text().splitlines() if line.strip()]


def _yes(system: str, user: str, prefix: str = llm.ANSWER) -> bool:
    out = llm.complete(system, user, max_tokens=4, prefix=prefix).strip().lower()
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


def retrieval_metrics(r: Retriever) -> dict:
    """Search quality only (no LLM calls, a few seconds): mean BM25/hybrid precision@5 and recall@10 over the answerable
    questions against the judged labels. Used to compare settings before and after a change."""
    js = _load_judgments()
    totals: dict[str, list[float]] = {}
    for q in questions():
        if not q["answerable"]:
            continue
        R = {c for (qid, c), j in js.items() if qid == q["id"] and j["relevant"]}
        bm = [h.chunk_id for h in _search(r, q["question"], POOL_K, False)]
        hy = [h.chunk_id for h in _search(r, q["question"], POOL_K, True)]
        for k, v in (("bm25_p5", _prec(bm[:5], R)), ("hybrid_p5", _prec(hy[:5], R)),
                     ("bm25_r10", _rec(bm, R)), ("hybrid_r10", _rec(hy, R))):
            if v is not None:
                totals.setdefault(k, []).append(v)
    return {k: round(sum(v) / len(v), 3) for k, v in totals.items()} | {"questions": len(totals.get("bm25_p5", []))}


def run(r: Retriever, answers: bool = True) -> tuple[str, dict]:
    """(markdown report, headline metrics). answers=False skips answering the questions (about 10 minutes with a
    local 27B model): the report then carries the previous run's answer metrics, dated."""
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
        # the gate asks the answer LLM (~14 s a question), so it runs only with the answers
        gated, how = answer.supporting(q["question"], _search(r, q["question"], 12, True)) if answers else ([], "")
        gate = [h.chunk_id for h in gated]
        unjudged = [c for c in set(bm[:5] + hy[:5] + gate) if (q["id"], c) not in js]
        m = {"bm25_p5": _prec(bm[:5], R), "hybrid_p5": _prec(hy[:5], R), "bm25_r10": _rec(bm[:10], R),
             "hybrid_r10": _rec(hy[:10], R), "gate_prec": _prec(gate, R) if answers else None, "gate_n": len(gate)}
        rows.append((q, len(R), m, how, unjudged))
        for k, v in m.items():
            if v is not None:
                totals.setdefault(k, []).append(v)
    ans, verdicts = [], []
    independent = llm.available(llm.JUDGE)
    for q in qs if answers else []:
        t = time.time()
        out = answer.ask(r, q["question"])
        secs = time.time() - t
        cites = out["citations"]
        sup, ind = [], []
        for s in out["answer"]:
            prompt = "Passages:\n" + "\n\n".join(cites[c]["quote"] for c in s["citations"]) + f"\n\nStatement: {s['text']}"
            sup.append(_yes(_SUP, prompt))
            ind.append(_yes(_SUP, prompt, llm.JUDGE) if independent else None)
            verdicts.append({"qid": q["id"], "sentence": s["text"],
                             "passages": {cites[c]["id"]: cites[c]["quote"] for c in s["citations"]},
                             "answer_llm": sup[-1], "independent": ind[-1]})
        ans.append((q, out["unsupported"], len(sup), sum(sup), secs, sum(ind) if independent else None))
    if verdicts:
        FAITHFULNESS.write_text("".join(json.dumps(v) + "\n" for v in verdicts))
    headline = _headline(rows, totals, ans, len(js))
    previous = _history()[-1] if _history() else None
    return _report(rows, totals, ans, len(js), headline, previous, feedback.summary()), headline


def _headline(rows, totals, ans, n_judged) -> dict:
    mean = lambda k: round(sum(totals[k]) / len(totals[k]), 3) if totals.get(k) else None  # noqa: E731
    h = {"time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "judged_pairs": n_judged,
         "unjudged_in_results": sum(len(u) for *_, u in rows),
         **{k: mean(k) for k in ("bm25_p5", "hybrid_p5", "bm25_r10", "hybrid_r10", "gate_prec")}}
    if ans:
        answerable = [a for a in ans if a[0]["answerable"]]
        traps = [a for a in ans if not a[0]["answerable"]]
        n_sent = sum(a[2] for a in answerable)
        h |= {"answered": sum(not a[1] for a in answerable), "answerable": len(answerable),
              "supported_sentences": sum(a[3] for a in answerable), "sentences": n_sent,
              "supported_independent": (sum(a[5] for a in answerable) if all(a[5] is not None for a in ans) else None),
              "independent_judge": llm.model_name(llm.JUDGE),
              "refused_traps": sum(a[1] for a in traps), "traps": len(traps),
              "median_seconds": round(sorted(a[4] for a in ans)[len(ans) // 2], 1)}
    return h


def _history() -> list[dict]:
    return [json.loads(line) for line in HISTORY.read_text().splitlines() if line.strip()] if HISTORY.exists() else []


def record(headline: dict) -> None:
    with HISTORY.open("a") as f:
        f.write(json.dumps(headline) + "\n")


def _prec(ids: list[str], rel: set[str]) -> float | None:
    return sum(c in rel for c in ids) / len(ids) if ids else None


def _rec(ids: list[str], rel: set[str]) -> float | None:
    return sum(c in rel for c in ids) / len(rel) if rel else None


def _report(rows, totals, ans, n_judged, h: dict, prev: dict | None, fb: dict) -> str:
    f = lambda v: "–" if v is None else f"{v:.2f}"  # noqa: E731
    last_answers = next((x for x in reversed(_history()) if "answered" in x), None)
    a = h if "answered" in h else last_answers
    lines = [
        f"# Evaluation report ({h['time']})",
        "",
        f"Models: answers and relevance judge `{llm.model_name()}`; embeddings `{embed.model_name()}`; decision `{decide.api_base()}`.",
        f"{len(rows)} answerable questions; {n_judged} judged (question, passage) pairs"
        + (f"; {h['unjudged_in_results']} passages in today's results are not judged yet (run `evaluate judge`)."
           if h["unjudged_in_results"] else "."),
        "Recall is against the pooled relevant set (BM25 top 10 + hybrid top 10), so it is an upper bound.",
        "Relevance judge vs hand checks of 60 judgments: 54/60 agree (28/30 and 26/30), 5 of the 6 misses lenient "
        "(eval/judge_check.md).",
        (f"Faithfulness is judged by the answer model and by an independent model, `{a.get('independent_judge')}`."
         if a and a.get("supported_independent") is not None else
         "Faithfulness is judged by the same model that writes the answers, which may favour its own sentences."),
        "",
        "## Retrieval",
        "",
        "| metric | now | previous run |",
        "|---|---|---|",
    ]
    for k, label in [("bm25_p5", "BM25 precision@5"), ("hybrid_p5", "Hybrid precision@5"), ("bm25_r10", "BM25 recall@10"),
                     ("hybrid_r10", "Hybrid recall@10"), ("gate_prec", "Evidence gate precision")]:
        now = f(h[k])
        if h[k] is None and k == "gate_prec" and last_answers and last_answers.get(k) is not None:
            now = f"{f(last_answers[k])} (not re-run; from {last_answers['time']})"  # the gate runs with the answers
        lines.append(f"| {label} | {now} | {f(prev.get(k)) if prev else '–'} |")
    lines += ["", "## Answers", ""]
    if a is None:
        lines.append("Not evaluated yet (run `python -m procintel.evaluate run`).")
    else:
        lines += [("Measured in this run." if a is h else f"Not re-run this time; figures from {a['time']}."), "",
                  "| metric | value |", "|---|---|",
                  f"| Answerable questions answered (not refused) | {a['answered']}/{a['answerable']} |",
                  f"| Answer sentences supported by their citations (answer model as judge) | {a['supported_sentences']}/{a['sentences']} |",
                  *([f"| Answer sentences supported by their citations (independent judge) | {a['supported_independent']}/{a['sentences']} |"]
                    if a.get("supported_independent") is not None else []),
                  f"| Unanswerable questions refused | {a['refused_traps']}/{a['traps']} |",
                  f"| Median time per question | {a['median_seconds']} s |"]
    lines += ["", "## User feedback", ""]
    ratings = {}
    for kind, rating, n in fb["ratings"]:
        ratings.setdefault(kind, {})[rating] = n
    if not fb["responses"]:
        lines.append("No responses logged yet.")
    else:
        lines += [f"{fb['responses']} responses logged.", "", "| page | useful | not useful | citations flagged |", "|---|---|---|---|"]
        for kind in ("ask", "assess"):
            r = ratings.get(kind, {})
            lines.append(f"| {kind} | {r.get('useful', 0)} | {r.get('not_useful', 0)} | {r.get('bad_citation', 0)} |")
        if fb["flagged_citations"]:
            lines += ["", "Most flagged citations (candidates for the evaluation set or the chunker):", ""]
            lines += [f"- `{cid}` flagged {n}×" for cid, n in fb["flagged_citations"]]
    lines += ["", "## Per question", "",
              "| id | question | relevant in pool | BM25 P@5 | hybrid P@5 | gate kept / precision | answer |",
              "|---|---|---|---|---|---|---|"]
    by_q = {x[0]["id"]: x for x in ans}
    for q, n_rel, m, how, unjudged in rows:
        x = by_q.get(q["id"])
        res = "–" if x is None else "refused" if x[1] else f"{x[3]}/{x[2]} supported"
        lines.append(f"| {q['id']} | {q['question']} | {n_rel} | {f(m['bm25_p5'])} | {f(m['hybrid_p5'])} | "
                     f"{m['gate_n']} / {f(m['gate_prec'])}{' (unjudged: ' + str(len(unjudged)) + ')' if unjudged else ''} | {res} |")
    for q, unsupported, n, k, *_ in [x for x in ans if not x[0]["answerable"]]:
        lines.append(f"| {q['id']} | {q['question']} | – | – | – | – | {'refused' if unsupported else f'ANSWERED ({k}/{n} supported)'} |")
    return "\n".join(lines) + "\n"


def report(r: Retriever, answers: bool = True) -> dict:
    """Run the evaluation, write eval/report.md and append to eval/history.jsonl; returns the headline metrics."""
    text, headline = run(r, answers)
    REPORT.write_text(text)
    record(headline)
    return headline


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    r = Retriever()
    if cmd == "judge":
        judge(r)
    elif cmd == "sample":
        sample(r)
    else:
        report(r, answers="--no-answers" not in sys.argv)
        print(REPORT.read_text())


if __name__ == "__main__":
    main()
