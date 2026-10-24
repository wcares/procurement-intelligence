"""Decision support for a planned procurement (the `/assess` endpoint): timeline benchmark, risk flags,
governance context and precedent passages. Rules mirror web/src/lib/mock/engine.ts so the mock and the
live API agree on everything except where the evidence comes from."""
from __future__ import annotations

from datetime import date

from procintel.answer import citation, meta, retrieval_note, terms
from procintel.retrieve import Retriever
from procintel.stats import MIN_BENCH_N, PROC_GROUP_LABELS
from procintel.tag import NONE

# A passage tagged "none of these" at this confidence describes no problem and is not offered as a precedent.
# Measured over all 18,140 tagged passages: at 0.9 the filter drops 3,549, of which 1.8% mention problem words
# (delay, termination, cancellation); at 0.5 it would drop 13,049 with 5.6%, several of them real lessons.
NOT_A_LESSON_MIN = 0.9

STALE_CPIA_YEARS = 5
# planners describe the package; the ICR passages that help them talk about what went wrong
_PRECEDENT_TERMS = "procurement delays contract bidding tender award"


def timeline(bench: dict, group: str, method: str) -> dict | None:
    label = PROC_GROUP_LABELS.get(group, group)
    for key, scope in ((f"{group}/{method}", f"{label} via {method}"), (group, f"all {label} packages"), ("all", "all packages")):
        b = bench.get(key)
        if b and b["n"] >= MIN_BENCH_N:
            return {"metric": "tender_to_award_days", "scope": scope, "n": b["n"], "median": b["median"],
                    "p25": b["p25"], "p75": b["p75"], "p90": b["p90"]}
    return None


def risks(bench: dict, group: str, method: str, t: dict | None, gov: list[dict]) -> list[dict]:
    out = []
    b = bench.get(f"{group}/{method}") or bench.get(group)
    if b and b["n"] >= MIN_BENCH_N:
        share = b["shareOver180"]
        out.append({"id": "long-cycle", "label": "Award takes longer than 6 months",
                    "level": "high" if share > 0.35 else "medium" if share > 0.2 else "low", "basis": "statistic",
                    "detail": f"{round(share * 100)}% of {b['n']} comparable packages took more than 180 days from tender notice to award."})
    if t and t["median"] > 0 and t["p90"] / t["median"] > 2.5:
        out.append({"id": "spread", "label": "Unpredictable timeline", "level": "medium", "basis": "statistic",
                    "detail": f"The slowest 10% took over {round(t['p90'])} days, {t['p90'] / t['median']:.1f}× the median of "
                              f"{round(t['median'])}. Plan buffer time."})
    tran = next((g for g in gov if g["indicator"] == "transparency_corruption"), None)
    if tran and tran["value"] < 3:
        out.append({"id": "governance", "label": "Low public-sector transparency score",
                    "level": "high" if tran["value"] < 2.5 else "medium", "basis": "statistic",
                    "detail": f"CPIA transparency/corruption rating {tran['value']} ({tran['year']}) on a 1–6 scale. Consider more prior review."})
    return out


def _lessons(hits: list) -> list:
    """Drop passages the tagger is confident describe no problem (indicator lists, staffing, outputs); keep untagged."""
    return [h for h in hits if not (h.tag == NONE and h.tag_confidence >= NOT_A_LESSON_MIN)]


def precedents(retriever: Retriever, country: str, group: str, description: str, sector: str) -> tuple[list[dict], bool, str]:
    """(precedents, widened, how they were retrieved): widened is True when the country had too few passages and all
    countries were searched."""
    query = f"{description} {sector} {PROC_GROUP_LABELS.get(group, '')} {_PRECEDENT_TERMS}"
    hits = _lessons(retriever.search(query, k=12, country=country, proc_group=group))[:5]
    widened = len(hits) < 3
    if widened:
        seen = {h.chunk_id for h in hits}
        more = _lessons(retriever.search(query, k=16, proc_group=group))
        hits += [h for h in more if h.chunk_id not in seen][: 5 - len(hits)]
    if not hits:
        return [], widened, retrieval_note([])
    top = max(h.score for h in hits)
    want = terms(f"{description} {sector}")
    out = []
    for h in hits:
        matched = ["same country" if h.country_code == country else "other country",
                   f"{PROC_GROUP_LABELS.get(group, group)} terms"]
        shared = sorted(want & terms(h.text))
        if shared:
            matched.append("terms: " + ", ".join(shared[:4]))
        out.append({"citation": citation(h), "relevance": round(h.score / top, 3), "matchedOn": matched})
    return out, widened, retrieval_note(hits)


def assess(retriever: Retriever, bench: dict, governance: dict, req: dict) -> dict:
    country, group, method = req["countryCode"], req["procGroup"], req["methodCode"]
    gov = governance.get(country, [])
    t = timeline(bench, group, method)
    precs, widened, how = precedents(retriever, country, group, req.get("description") or "", req.get("sector") or "")
    caveats = ["Timeline and risk numbers are statistics over historical World Bank procurement notices in the "
               "ingested sample; precedents are ICR evaluation passages.", how]
    if not gov:
        caveats.append("No CPIA governance scores are available for this country.")
    elif (old := min(g["year"] for g in gov)) < date.today().year - STALE_CPIA_YEARS:
        caveats.append(f"The latest CPIA scores for this country date from {old}; treat the governance flag as dated.")
    if t and " via " not in t["scope"]:
        caveats.append("Too few packages for this exact method; the timeline uses a wider slice.")
    if widened:
        caveats.append("Few evaluation passages for this country; precedents include other countries.")
    return {"timeline": t, "risks": risks(bench, group, method, t, gov), "governance": gov,
            "precedents": precs, "meta": meta(caveats)}
