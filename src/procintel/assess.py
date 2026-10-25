"""Decision support for a planned procurement (the `/assess` endpoint): timeline benchmark, risk flags,
governance context and precedent passages. Rules mirror web/src/lib/mock/engine.ts so the mock and the
live API agree on everything except where the evidence comes from."""
from __future__ import annotations

from datetime import date

from procintel import answer, decide
from procintel.answer import citation, conflict_notes, meta, retrieval_note, terms
from procintel.retrieve import Retriever
from procintel.stats import MIN_BENCH_N, PROC_GROUP_LABELS
from procintel.predict import LONG_DAYS, predict_one
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


def _relevant(hits: list, package: str) -> tuple[list, int]:
    """(hits the decision model judges a useful lesson for this package, number dropped); all hits without a model."""
    if not decide.available():
        return hits, 0
    q = "Does the passage describe an experience or lesson that would help plan this procurement?"
    try:
        keep = [h for h in hits if decide.yes(f"Planned procurement: {package}\nPassage: {h.text}", q) >= answer.DECIDE_MIN]
    except Exception:  # decision server down: keep the retrieval order rather than fail the assessment
        return hits, 0
    return keep, len(hits) - len(keep)


def precedents(retriever: Retriever, country: str, group: str, description: str, sector: str,
               country_name: str = "", method: str = "") -> tuple[list[dict], bool, str, list[str]]:
    """(precedents, widened, how they were retrieved, conflict notes): widened is True when the country had too few
    passages and all countries were searched. With a decision model, each candidate must be judged a useful lesson
    for the planned package (it dropped indicator and disbursement tables that retrieval ranked first)."""
    query = f"{description} {sector} {PROC_GROUP_LABELS.get(group, '')} {_PRECEDENT_TERMS}"
    package = ", ".join(x for x in [f"{PROC_GROUP_LABELS.get(group, group)} by {method or 'unspecified method'}",
                                    f"in {country_name or country}", sector, description] if x)
    candidates = _lessons(retriever.search(query, k=12, country=country, proc_group=group))
    judged = {h.chunk_id for h in candidates}  # judged once: a rejected passage must not come back in the wider search
    hits, dropped = _relevant(candidates, package)
    hits = hits[:5]
    widened = len(hits) < 3
    if widened:
        more, d2 = _relevant([h for h in _lessons(retriever.search(query, k=16, proc_group=group)) if h.chunk_id not in judged], package)
        hits += more[: 5 - len(hits)]
        dropped += d2
    how = retrieval_note(hits) + (f" The decision model set aside {dropped} retrieved passages as not a useful lesson "
                                  "for this package." if dropped else "")
    if not hits:
        return [], widened, how, []
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
    return out, widened, how, conflict_notes(retriever, hits)


def model_flags(bundle: dict | None, req: dict, region: str | None, gov: list[dict], t: dict | None) -> list[dict]:
    """Risk flags from the trained timeline model (procintel.predict), only for targets where it beat the baseline."""
    if not bundle:
        return []
    use, m = bundle["use"], bundle["metrics"]
    if not (use.get("days_p50") or use.get("over_180")):
        return []
    row = {"proc_group": req["procGroup"], "method_code": req["methodCode"], "region": region,
           "sector": req.get("sector") or None, "tender_start": date.today().isoformat(),
           "value_usd": req.get("estimatedValueUsd")}
    row.update({f"cpia_{g['indicator']}": g["value"] for g in gov})
    p = predict_one(bundle, row)
    tested = f"tested on {bundle['n']} past packages from projects it had not seen"
    out = []
    if use.get("days_p50"):
        days = round(p["p50"])
        vs = f"; the historical median for comparable packages is {round(t['median'])}" if t else ""
        if not req.get("estimatedValueUsd"):
            vs += "; no contract value was given, so the typical value for this procurement type and method was used"
        out.append({"id": "model-timeline", "label": f"Predicted award time: about {days} days", "basis": "model",
                    "level": "high" if days > LONG_DAYS else "medium" if days > 120 else "low",
                    "detail": f"Model estimate for this package{vs}."
                              + (f" Slow case (1 in 10 take longer): about {round(p['p90'])} days." if use.get("days_p90") else "")
                              + f" Typical error {m['days_p50_mae'][0]:.0f} days, "
                              f"vs {m['days_p50_mae'][1]:.0f} for the historical median ({tested})."})
    if use.get("over_180"):
        pl = p["p_long"]
        out.append({"id": "model-long", "label": f"Risk award takes longer than 6 months: {pl:.0%}", "basis": "model",
                    "level": "high" if pl > 0.35 else "medium" if pl > 0.2 else "low",
                    "detail": f"Model probability for this package. It ranks slow packages better than the historical "
                              f"share (AUC {m['over_180_auc'][0]:.2f} vs {m['over_180_auc'][1]:.2f}; {tested})."})
    return out


def assess(retriever: Retriever, bench: dict, governance: dict, req: dict, model: dict | None = None,
           region: str | None = None, country_name: str = "") -> dict:
    country, group, method = req["countryCode"], req["procGroup"], req["methodCode"]
    gov = governance.get(country, [])
    t = timeline(bench, group, method)
    precs, widened, how, conflicts = precedents(retriever, country, group, req.get("description") or "",
                                                req.get("sector") or "", country_name, method)
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
    caveats += conflicts
    flags = model_flags(model, req, region, gov, t)
    if flags:
        caveats.append(f"Flags marked 'model' come from gradient-boosted trees trained on {model['n']} past packages "
                       "(procurement type, method, region, sector, year, CPIA). They are estimates, not commitments.")
    return {"timeline": t, "risks": risks(bench, group, method, t, gov) + flags, "governance": gov,
            "precedents": precs, "meta": meta(caveats)}
