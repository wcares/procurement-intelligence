"""What the Evaluation page shows (docs/ui-design.md 3b), assembled from where each result already lives:

    quality     eval/history.jsonl, one line per evaluation run, each with the changes made since the run before
                (refreshes, retrains, promotions, prompt activations, pipeline batches), so a change in a measure can
                be read against what caused it
                (and when the question set itself changed, which moves the measures too)
    comparisons live vs shadow index builds (procintel.learning.shadows), active vs candidate prompt versions
                (procintel.core.prompts), and runs with another model (eval/history-<model>.jsonl) against the live
                run closest before them on the same question set
    models      the timeline model per retrain (data/models/history.jsonl; the saved model and recent retrain jobs fill
                in what predates that file) and the latest drift checks
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from procintel.core import paths, prompts
from procintel.jobs import store as jobs_store
from procintel.learning import evaluate, shadows
from procintel.prediction import predict

CHANGE_KINDS = {"refresh": "data refresh", "retrain": "timeline model retrained", "shadow_promote": "shadow promoted",
                "pipeline_batch": "pipeline changes applied"}


def _t(s: str) -> datetime:
    """'2026-10-25 02:04 UTC' (evaluation history) or ISO, as naive UTC."""
    s = s.replace(" UTC", "").replace("Z", "").replace("+00:00", "")
    return datetime.fromisoformat(s)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def _jobs(kinds: list[str], limit: int = 500, db_path: Path | None = None) -> list[dict]:
    con = jobs_store._connect(db_path)
    try:
        q = con.execute("SELECT id, kind, reason, finished_at, result FROM jobs WHERE status = 'done' AND kind IN "
                        "(SELECT unnest(?)) ORDER BY finished_at DESC LIMIT ?", [kinds, limit])
        return [{"id": i, "kind": k, "reason": r, "at": f, "result": json.loads(res) if res else None}
                for i, k, r, f, res in q.fetchall()]
    finally:
        con.close()


def changes(db_path: Path | None = None) -> list[dict]:
    """Things that can move the measures, newest first."""
    out = [{"at": j["at"], "what": CHANGE_KINDS[j["kind"]], "detail": j["reason"]}
           for j in _jobs(list(CHANGE_KINDS), db_path=db_path)]
    for p in prompts.listing():
        for v in p["versions"]:
            if v.get("activated"):
                out.append({"at": _t(v["activated"]), "what": "prompt activated",
                            "detail": f"{p['label']} version {v['version']}"})
    for s in shadows.states():
        if s.get("promoted_at"):
            out.append({"at": _t(s["promoted_at"]), "what": "shadow promoted", "detail": s.get("label") or s["name"]})
    return sorted(out, key=lambda c: c["at"], reverse=True)


def quality(db_path: Path | None = None) -> list[dict]:
    """Evaluation runs oldest first, each with the changes since the run before it."""
    runs = evaluate._history()
    found = changes(db_path)
    out, prev, seen = [], None, {}
    for r in runs:
        at = _t(r["time"])
        since = [c for c in found if (prev is None or c["at"] > prev) and c["at"] <= at]
        events = [{"at": c["at"].isoformat() + "Z", "what": c["what"], "detail": c["detail"]} for c in reversed(since)]
        for key, words in SET_FIELDS.items():   # the measures move when the question set changes, not the system
            if r.get(key) is not None:
                if seen.get(key) is not None and r[key] != seen[key]:
                    events.append({"at": at.isoformat() + "Z", "what": "evaluation set changed",
                                   "detail": f"{words}: {seen[key]} → {r[key]}"})
                seen[key] = r[key]
        out.append({**r, "changesBefore": events})
        prev = at
    return out


SET_FIELDS = {"answerable": "answerable questions", "traps": "trap questions", "judged_pairs": "judged passages"}


def same_set(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in SET_FIELDS)


def other_model_runs() -> list[dict]:
    """eval/history-<name>.jsonl: the newest run with that model beside the live run closest before it."""
    live = evaluate._history()
    out = []
    for f in sorted(paths.EVAL_DIR.glob("history-*.jsonl")):
        runs = _jsonl(f)
        if not runs:
            continue
        run = runs[-1]
        before = [r for r in live if _t(r["time"]) <= _t(run["time"]) and same_set(r, run)]   # same questions only
        out.append({"name": f.stem.removeprefix("history-"), "run": run, "live": before[-1] if before else None})
    return out


def comparisons() -> dict:
    prompt_evals = [{"name": p["name"], "label": p["label"], "active": p["active"], "version": v["version"],
                     "note": v.get("note"), "evaluation": v["evaluation"]}
                    for p in prompts.listing() for v in p["versions"] if v.get("evaluation") and not v["active"]]
    return {"shadows": shadows.states(), "shadowKinds": [{"name": s.name, "label": s.label}
                                                         for s in shadows.SHADOWS.values()],
            "prompts": prompt_evals, "models": other_model_runs()}


def models(db_path: Path | None = None) -> dict:
    rows = _jsonl(predict.MODEL_HISTORY)
    known = {r["trained_at"][:16] for r in rows}
    bundle = predict.load()
    if bundle and bundle["trained_at"][:16] not in known:            # trained before the history file existed
        rows.append(predict.history_row(bundle) | {"source": "the saved model"})
        known.add(bundle["trained_at"][:16])
    for j in _jobs(["retrain"], db_path=db_path):                     # earlier retrains: what their job kept
        at = j["at"].isoformat()
        if j["result"] and at[:16] not in known:
            rows.append({"trained_at": at + "+00:00", "n": j["result"].get("n"),
                         "metrics": {"days_p50_mae": j["result"].get("days_p50_mae")}, "source": "retrain job"})
    rows.sort(key=lambda r: r["trained_at"])
    drift = [{"at": j["at"].isoformat() + "Z", **(j["result"] or {})} for j in _jobs(["drift_check"], 10, db_path)]
    return {"retrains": rows, "driftChecks": drift}


def page(db_path: Path | None = None) -> dict:
    return {"quality": quality(db_path), "comparisons": comparisons(), "models": models(db_path)}
