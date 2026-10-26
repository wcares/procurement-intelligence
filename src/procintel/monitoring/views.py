"""What the monitoring screens show (tracker U9): projects with their packages' statuses, one project, one package with
its notices and live forecast, and a forecast for a package a planner describes. Everything is recomputed from the
current data on each call (all packages are classified in about 0.1 s); stale packages are kept out of the history the
forecasts compare with."""
from __future__ import annotations

from datetime import date

import pandas as pd

from procintel.core import db
from procintel.monitoring import forecast, isr_ratings, status


def _iso(v):
    return None if v is None or (not isinstance(v, str) and pd.isna(v)) else (v.date().isoformat() if hasattr(v, "date") else str(v))


def _classified() -> pd.DataFrame:
    return status.classify(status.frame())


def _reissued(package_ids: list[str]) -> set[str]:
    if not package_ids:
        return set()
    con = db.connect(read_only=True)
    try:
        return {p for (p,) in con.execute("SELECT package_id FROM notice_m WHERE package_id IN (SELECT unnest(?)) "
                                          "GROUP BY 1 HAVING max(notice_version) >= 1", [package_ids]).fetchall()}
    finally:
        con.close()


def _facts(r, reissued: bool) -> dict:
    start = r.tender_start if pd.notna(r.tender_start) else r.first_notice
    return {"proc_group": r.proc_group, "method_code": r.method_code, "tender_start": _iso(start),
            "award_date": _iso(r.award_date) if pd.notna(r.award_date) else None,
            "contract_duration_days": None if pd.isna(r.contract_duration_days) else float(r.contract_duration_days),
            "reissued": reissued, "closing_date": _iso(r.closing_date) if pd.notna(r.closing_date) else None}


def _package_json(r, f: dict | None) -> dict:
    return {"packageId": r.package_id, "projectId": r.project_id, "description": r.description, "procGroup": r.proc_group,
            "methodCode": r.method_code, "status": r.status, "phase": r.phase, "reason": r.reason, "ageDays": r.age_days,
            "tenderStart": _iso(r.tender_start) if pd.notna(r.tender_start) else _iso(r.first_notice),
            "awardDate": _iso(r.award_date) if pd.notna(r.award_date) else None, "lastNotice": _iso(r.last_notice),
            "contractEnd": r.contract_end, "forecast": f, "warnings": [w["kind"] for w in (f or {}).get("warnings", [])]}


def projects(only: list[str] | None = None) -> list[dict]:
    """Projects with active packages (or the given ones), each with its packages by status and its warnings count."""
    cl = _classified()
    hist = cl[cl.status != "stale"]
    active = cl[cl.status == "active"]
    if only is not None:
        cl = cl[cl.project_id.isin(only)]
    keep = set(only) if only is not None else set(active.project_id)
    rows = [p for p in status.rollup(cl) if p["projectId"] in keep]
    isr = isr_ratings.latest([p["projectId"] for p in rows])
    rei = _reissued(list(active[active.project_id.isin(keep)].package_id))
    for p in rows:
        warn = 0
        for r in active[active.project_id == p["projectId"]].itertuples(index=False):
            warn += bool(forecast.forecast(_facts(r, r.package_id in rei), hist, isr=isr.get(p["projectId"]))["warnings"])
        p["packagesWithWarnings"] = warn
        p["isr"] = isr.get(p["projectId"])
    return sorted(rows, key=lambda p: (-p["packagesWithWarnings"], -p["packages"]["active"], p["projectId"]))


def project(project_id: str) -> dict | None:
    cl = _classified()
    mine = cl[cl.project_id == project_id]
    if mine.empty:
        return None
    hist = cl[cl.status != "stale"]
    isr = isr_ratings.latest([project_id]).get(project_id)
    rei = _reissued(list(mine.package_id))
    pkgs = []
    for r in mine.itertuples(index=False):
        f = forecast.forecast(_facts(r, r.package_id in rei), hist, isr=isr) if r.status == "active" else None
        pkgs.append(_package_json(r, f))
    order = {"active": 0, "stale": 1, "replaced": 2, "finished": 3}
    pkgs.sort(key=lambda p: (order[p["status"]], -len(p["warnings"]), p["packageId"]))
    head = status.rollup(mine)[0]
    return head | {"isr": isr, "packageList": pkgs}


def package(package_id: str) -> dict | None:
    cl = _classified()
    row = cl[cl.package_id == package_id]
    if row.empty:
        return None
    r = next(row.itertuples(index=False))
    hist = cl[cl.status != "stale"]
    isr = isr_ratings.latest([r.project_id]).get(r.project_id)
    f = forecast.forecast(_facts(r, bool(_reissued([package_id]))), hist, isr=isr) if r.status == "active" else None
    con = db.connect(read_only=True)
    try:
        notices = [{"noticeId": i, "type": t, "date": d, "version": v, "awardDate": a} for i, t, d, v, a in con.execute(
            "SELECT notice_id, notice_type, notice_date::DATE::VARCHAR, notice_version, award_date::DATE::VARCHAR "
            "FROM notice_m WHERE package_id = ? ORDER BY notice_date", [package_id]).fetchall()]
    finally:
        con.close()
    return _package_json(r, f) | {"projectName": r.project_name, "closingDate": _iso(r.closing_date) if pd.notna(r.closing_date) else None,
                                  "notices": notices, "isr": isr}


def describe(facts: dict, today: date | None = None) -> dict:
    """A forecast for a package a planner describes (what they know now)."""
    cl = _classified()
    return forecast.forecast(facts, cl[cl.status != "stale"], today)
