"""Pilot KPIs that the logs can already answer (docs/pilot-plan.md defines all of them and what each still needs).

Per ISO week, from data/feedback.duckdb: responses by page, active users (pseudonymous ids), the share of Ask questions
refused, the share of responses rated, the share of ratings that say "useful", citations flagged as wrong, and the
median response time with the share over a minute. award_error() compares the award time an assessment predicted with
the actual one, for assessments that named their tender and whose tender has since been awarded. Quality KPIs (retrieval precision and
recall, faithfulness, refusals on traps) come from `python -m procintel.learning.evaluate run`, not from here.

    python -m procintel.learning.kpi
"""
from __future__ import annotations

from pathlib import Path

from procintel.core import db
from procintel.learning import feedback


def weekly(db_path: Path | None = None) -> list[dict]:
    path = db_path or feedback.DB_PATH
    if not Path(path).exists():
        return []
    con = feedback._connect(Path(path))  # adds columns newer than the log (user_id, duration_ms) before reading
    try:
        rows = con.execute("""
            WITH r AS (
                SELECT response_id, kind, strftime(created_at, '%G-W%V') AS week, user_id, duration_ms,
                       kind = 'ask' AND json_extract(response, '$.unsupported')::BOOLEAN AS refused
                FROM response_log),
            f AS (
                SELECT response_id, count(*) FILTER (WHERE rating IN ('useful', 'not_useful')) AS rated,
                       count(*) FILTER (WHERE rating = 'useful') AS useful,
                       count(*) FILTER (WHERE rating = 'bad_citation') AS flagged
                FROM feedback GROUP BY 1)
            SELECT week,
                   count(*) FILTER (WHERE kind = 'assess') AS assess,
                   count(*) FILTER (WHERE kind = 'ask') AS ask,
                   count(*) FILTER (WHERE refused) AS ask_refused,
                   count(*) FILTER (WHERE coalesce(f.rated, 0) > 0) AS responses_rated,
                   coalesce(sum(f.useful), 0) AS useful,
                   coalesce(sum(f.rated), 0) AS ratings,
                   coalesce(sum(f.flagged), 0) AS citations_flagged,
                   count(DISTINCT user_id) AS active_users,
                   median(duration_ms) / 1000.0 AS median_seconds,
                   count(*) FILTER (WHERE duration_ms > 60000) AS over_minute,
                   count(duration_ms) AS timed
            FROM r LEFT JOIN f USING (response_id)
            GROUP BY week ORDER BY week""").fetchall()
    finally:
        con.close()
    out = []
    for week, assess, ask, refused, rated, useful, ratings, flagged, users, med, over, timed in rows:
        out.append({"week": week, "assess": assess, "ask": ask,
                    "ask_refusal_rate": round(refused / ask, 3) if ask else None,
                    "rated_share": round(rated / (assess + ask), 3) if assess + ask else None,
                    "useful_share": round(useful / ratings, 3) if ratings else None,
                    "citations_flagged": flagged, "active_users": users,
                    "median_seconds": round(med, 1) if med is not None else None,
                    "over_minute_share": round(over / timed, 3) if timed else None})
    return out


def _key(ref: str) -> str:
    return "".join(ref.split()).upper()


def award_error(feedback_db: Path | None = None, main_db: Path | None = None) -> dict:
    """Predicted vs actual tender-to-award days for assessments that gave a tender reference: matched on the bid
    reference (the part of a package id after the project, compared without spaces or case). Pending = named a tender
    that has no award time yet (not awarded, or not in the data yet)."""
    path = feedback_db or feedback.DB_PATH
    if not Path(path).exists():
        return {"named": 0, "matched": 0, "pending": 0}
    con = feedback._connect(Path(path))
    try:
        named = con.execute("""
            SELECT json_extract_string(request, '$.tenderReference') AS ref,
                   json_extract(response, '$.prediction.days_p50')::DOUBLE AS predicted,
                   json_extract_string(response, '$.prediction.basis') AS basis
            FROM response_log
            WHERE kind = 'assess' AND nullif(trim(json_extract_string(request, '$.tenderReference')), '') IS NOT NULL
              AND json_extract(response, '$.prediction.days_p50') IS NOT NULL""").fetchall()
    finally:
        con.close()
    if not named:
        return {"named": 0, "matched": 0, "pending": 0}
    mcon = db.connect(main_db, read_only=True) if main_db else db.connect(read_only=True)
    try:
        actual = {_key(ref): days for ref, days in mcon.execute(
            "SELECT split_part(package_id, '/', 2), tender_to_award_days FROM package "
            "WHERE tender_to_award_days IS NOT NULL").fetchall()}
    finally:
        mcon.close()
    pairs = [(basis, pred, actual[_key(ref)]) for ref, pred, basis in named if _key(ref) in actual]
    out: dict = {"named": len(named), "matched": len(pairs), "pending": len(named) - len(pairs)}
    for basis in sorted({b for b, _, _ in pairs}):
        errs = [abs(p - a) for b, p, a in pairs if b == basis]
        out[basis] = {"n": len(errs), "mean_abs_error_days": round(sum(errs) / len(errs), 1)}
    return out


def main() -> None:
    rows = weekly()
    if not rows:
        print("no responses logged yet")
        return
    fmt = lambda v: "–" if v is None else f"{v:.0%}" if isinstance(v, float) else str(v)  # noqa: E731
    print("week       assess  ask  users  ask refused  rated  useful  flagged  median s  over 60 s")
    for r in rows:
        med = "–" if r["median_seconds"] is None else f"{r['median_seconds']:.1f}"
        print(f"{r['week']:9s}  {r['assess']:6d}  {r['ask']:3d}  {r['active_users']:5d}  {fmt(r['ask_refusal_rate']):>11s}  "
              f"{fmt(r['rated_share']):>5s}  {fmt(r['useful_share']):>6s}  {r['citations_flagged']:7d}  {med:>8s}  "
              f"{fmt(r['over_minute_share']):>9s}")
    e = award_error()
    print(f"\naward time: {e['named']} assessments named their tender, {e['matched']} of those tenders have an award time "
          f"({e['pending']} pending)")
    for basis in ("model", "historical median"):
        if basis in e:
            print(f"  {basis}: mean absolute error {e[basis]['mean_abs_error_days']} days on {e[basis]['n']} packages")
    print("Responses logged before 2026-10-25 have no user id or response time.")


if __name__ == "__main__":
    main()
