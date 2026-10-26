"""Recommendations for a planned package (docs/ui-design.md 2.4), only from statistics and cited precedents; with no
supporting evidence, none is made.

    method       another method used for the same kind of purchase whose comparable packages were awarded clearly
                 faster (median at least FASTER shorter, both with at least MIN_BENCH_N packages). The Procurement
                 Regulations' value thresholds still decide which methods a package may use, and the note says so.
    mitigation   for the flagged risks (high first, at most MAX_RISKS), what past projects did about them: asked as a
                 question through the answer pipeline (procintel.answering.answer.ask) for the package's kind of
                 purchase, so every sentence cites the passage it comes from and was checked against it
"""
from __future__ import annotations

from procintel.answering import answer
from procintel.answering.retrieve import Retriever
from procintel.prediction.stats import MIN_BENCH_N, PROC_GROUP_LABELS

FASTER = 0.2
MAX_RISKS = 2
LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}


def method_alternatives(bench: dict, group: str, method: str, labels: dict[str, str]) -> list[dict]:
    mine = bench.get(f"{group}/{method}")
    if not mine or mine["n"] < MIN_BENCH_N:
        return []
    out = []
    for key, b in bench.items():
        g, _, m = key.partition("/")
        if g != group or not m or m == method or not b or b["n"] < MIN_BENCH_N:
            continue
        if b["median"] <= mine["median"] * (1 - FASTER):
            out.append({"kind": "method", "id": f"method:{m}",
                        "title": f"Consider {labels.get(m, m)} if the package qualifies",
                        "text": (f"In comparable {PROC_GROUP_LABELS.get(group, group).lower()} packages, "
                                 f"{labels.get(m, m)} took a median {b['median']:.0f} days from tender to award "
                                 f"(n={b['n']}) against {mine['median']:.0f} days for {labels.get(method, method)} "
                                 f"(n={mine['n']})."),
                        "note": "Which methods a package may use depends on its value and the Procurement Regulations' "
                                "thresholds; faster methods are often meant for smaller contracts.",
                        "basis": "statistic", "citations": []})
    return sorted(out, key=lambda r: r["text"])[:2]


def mitigations(retriever: Retriever, risks: list[dict], group: str) -> list[dict]:
    flagged = sorted([r for r in risks if r["level"] in ("high", "medium")], key=lambda r: LEVEL_ORDER[r["level"]])
    out = []
    for r in flagged[:MAX_RISKS]:
        q = (f"What did past projects do to prevent or reduce this problem in "
             f"{PROC_GROUP_LABELS.get(group, group).lower()} procurement: {r['label'].lower()}?")
        res = answer.ask(retriever, q, proc_group=group)
        if res["unsupported"] or not res["answer"]:
            continue
        out.append({"kind": "mitigation", "id": f"mitigation:{r['id']}", "title": f"Against: {r['label']}",
                    "question": q, "sentences": res["answer"], "citations": res["citations"], "basis": "precedents",
                    "risk": r["id"]})
    return out


def for_package(retriever: Retriever, bench: dict, body: dict, risks: list[dict], labels: dict[str, str]) -> dict:
    recs = method_alternatives(bench, body["procGroup"], body["methodCode"], labels)
    recs += mitigations(retriever, risks, body["procGroup"])
    return {"recommendations": recs,
            "meta": answer.meta(["Recommendations come only from the statistics and cited passages shown; none is "
                                 "made where the evidence does not support one."])}
