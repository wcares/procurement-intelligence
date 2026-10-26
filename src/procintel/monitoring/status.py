"""A status for every package of every tracked project, from what has been published so far and the parameters in
procintel.monitoring.status_rules. Checked in this order, the first that applies wins:

    replaced   a later package continues it (the original of an X / X-N pair, procintel.ingestion.tables)
    finished   its contract has ended: award date + stated duration (+ margin) passed, or, with no stated duration,
               award + the median duration of comparable contracts (estimate_contract_end)
    finished / stale   the project has ended (project_overrides: closed, closing date passed, completion report):
               finished when an award is recorded, stale when none is ("ended without a recorded award")
    active     awarded and the contract still running (phase "contract")
    stale      no award, and open longer than stale_quantile of comparable awarded tenders took, or than
               stale_max_days; or no dates at all
    active     no award yet and within those bounds (phase "bidding")

"Comparable" is the same procurement group and method with at least MIN_N awarded packages, else the group, else
all. Stale packages get no forecast and stay out of the statistics; the reason says which rule decided.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from procintel.core import db
from procintel.monitoring import status_rules

MIN_N = 10
ICR = "Implementation Completion and Results Report"
STATUSES = ("active", "finished", "replaced", "stale")


def frame(con=None) -> pd.DataFrame:
    own = con is None
    con = con or db.connect(read_only=True)
    try:
        return con.execute(f"""
            SELECT k.package_id, k.project_id, k.proc_group, k.method_code, k.description,
                   k.tender_start::DATE AS tender_start, k.award_date::DATE AS award_date,
                   k.tender_to_award_days, k.contract_duration_days, k.rebid_evidence,
                   n.first_notice, n.last_notice, n.n_notices,
                   p.name AS project_name, p.country_code, p.status AS project_status,
                   p.closing_date::DATE AS closing_date,
                   p.project_id IN (SELECT unnest(string_split(project_id, ',')) FROM documents WHERE doc_type = '{ICR}')
                       AS has_completion_report
            FROM package k JOIN projects p USING (project_id)
            LEFT JOIN (SELECT package_id, min(notice_date)::DATE AS first_notice, max(notice_date)::DATE AS last_notice,
                              count(*) AS n_notices FROM notice_m GROUP BY 1) n USING (package_id)""").df()
    finally:
        if own:
            con.close()


def _by_scope(df: pd.DataFrame, col: str, fn) -> dict:
    """{(group, method) | group | None: value of fn over the column}, for groups with at least MIN_N values."""
    d = df.dropna(subset=[col])
    out = {None: fn(d[col])} if len(d) else {}
    for g, f in d.groupby("proc_group"):
        if len(f) >= MIN_N:
            out[g] = fn(f[col])
    for (g, m), f in d.groupby(["proc_group", "method_code"]):
        if len(f) >= MIN_N:
            out[(g, m)] = fn(f[col])
    return out


def _lookup(table: dict, g, m):
    return table.get((g, m), table.get(g, table.get(None)))


def classify(df: pd.DataFrame, params: dict | None = None, today: date | None = None) -> pd.DataFrame:
    p = params or status_rules.active()
    today = pd.Timestamp(today or date.today())
    q = _by_scope(df, "tender_to_award_days", lambda s: float(s.quantile(p["stale_quantile"])))
    dur = _by_scope(df, "contract_duration_days", lambda s: float(s.median()))
    rows = []
    for r in df.itertuples(index=False):
        awarded = pd.notna(r.award_date)
        start = r.tender_start if pd.notna(r.tender_start) else r.first_notice
        stated = r.contract_duration_days if pd.notna(r.contract_duration_days) else None
        d = stated if stated is not None else (_lookup(dur, r.proc_group, r.method_code) if p["estimate_contract_end"] else None)
        end = pd.Timestamp(r.award_date) + pd.Timedelta(days=d) if awarded and d is not None else None
        ended = {"closed": r.project_status == "Closed",
                 "closing_passed": pd.notna(r.closing_date) and pd.Timestamp(r.closing_date) < today,
                 "completion_report": bool(r.has_completion_report)}
        over = [k for k in p["project_overrides"] if ended.get(k)]
        limit = _lookup(q, r.proc_group, r.method_code)
        if p["stale_max_days"] is not None:
            limit = min(limit, p["stale_max_days"]) if limit is not None else p["stale_max_days"]
        age = (today - pd.Timestamp(start)).days if pd.notna(start) else None
        if r.rebid_evidence == "successor_reference":
            st, phase, why = "replaced", None, "a later package with the same reference and a suffix continues it"
        elif end is not None and end + pd.Timedelta(days=p["contract_end_margin"]) < today:
            st, phase = "finished", None
            why = "contract ended " + ("(award + stated duration)" if stated is not None else
                                       f"(award + the median {d:.0f} days of comparable contracts: an estimate)")
        elif over:
            st, phase = ("finished", None) if awarded else ("stale", None)
            why = f"project ended ({', '.join(o.replace('_', ' ') for o in over)})" + ("" if awarded else
                                                                                       " without a recorded award")
        elif awarded:
            st, phase = "active", "contract"
            why = "awarded, contract running" + (f" until about {end.date()}" if end is not None else "")
        elif age is None:
            st, phase, why = "stale", None, "no award and no dates"
        elif limit is not None and age > limit:
            st, phase = "stale", None
            why = f"no award after {age} days, longer than {p['stale_quantile']:.0%} of comparable tenders took or " \
                  f"the {p['stale_max_days']}-day cap (limit {limit:.0f} days)"
        else:
            st, phase, why = "active", "bidding", f"no award yet, open {age} days (limit {limit:.0f})" if limit else \
                f"no award yet, open {age} days"
        rows.append({"package_id": r.package_id, "status": st, "phase": phase, "reason": why, "age_days": age,
                     "contract_end": end.date().isoformat() if end is not None else None,
                     "stale_limit_days": round(limit) if limit is not None else None})
    out = df.merge(pd.DataFrame(rows), on="package_id")
    for c in ("phase", "contract_end", "stale_limit_days", "age_days"):   # None, not NaN, where a value is missing
        out[c] = out[c].astype(object).where(out[c].notna(), None)
    return out


def counts(classified: pd.DataFrame) -> dict:
    c = classified.groupby(["status", "phase"], dropna=False).size()
    return {"status": {s: int(classified["status"].eq(s).sum()) for s in STATUSES},
            "phase": {str(ph): int(n) for (st, ph), n in c.items() if st == "active"}}


def rollup(classified: pd.DataFrame) -> list[dict]:
    """Per project: its packages by status, with the World Bank status and closing date."""
    out = []
    for pid, f in classified.groupby("project_id"):
        first = f.iloc[0]
        out.append({"projectId": pid, "name": first["project_name"], "countryCode": first["country_code"],
                    "projectStatus": first["project_status"],
                    "closingDate": first["closing_date"].isoformat() if pd.notna(first["closing_date"]) else None,
                    "packages": {s: int(f["status"].eq(s).sum()) for s in STATUSES},
                    "bidding": int(f["phase"].eq("bidding").sum())})
    return sorted(out, key=lambda r: (-r["packages"]["active"], r["projectId"]))


def dry_run(df: pd.DataFrame, candidate: dict, today: date | None = None) -> dict:
    """How many packages each change of parameters moves, from status to status."""
    now = classify(df, status_rules.active(), today)[["package_id", "status"]]
    new = classify(df, status_rules.DEFAULTS | candidate, today)[["package_id", "status"]]
    m = now.merge(new, on="package_id", suffixes=("_now", "_new"))
    moved = m[m.status_now != m.status_new].groupby(["status_now", "status_new"]).size()
    return {"now": counts(classify(df, status_rules.active(), today)), "candidate": counts(classify(df, status_rules.DEFAULTS | candidate, today)),
            "moves": [{"from": a, "to": b, "packages": int(n)} for (a, b), n in moved.items()]}
