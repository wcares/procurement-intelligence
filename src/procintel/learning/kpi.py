"""Pilot KPIs that the logs can already answer (docs/pilot-plan.md defines all of them and what each still needs).

Per ISO week, from data/feedback.duckdb: responses by page, the share of Ask questions refused, the share of responses
rated, the share of ratings that say "useful", and citations flagged as wrong. Quality KPIs (retrieval precision and
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
    con = db.connect(path, read_only=True)
    try:
        rows = con.execute("""
            WITH r AS (
                SELECT response_id, kind, strftime(created_at, '%G-W%V') AS week,
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
                   coalesce(sum(f.flagged), 0) AS citations_flagged
            FROM r LEFT JOIN f USING (response_id)
            GROUP BY week ORDER BY week""").fetchall()
    finally:
        con.close()
    out = []
    for week, assess, ask, refused, rated, useful, ratings, flagged in rows:
        out.append({"week": week, "assess": assess, "ask": ask,
                    "ask_refusal_rate": round(refused / ask, 3) if ask else None,
                    "rated_share": round(rated / (assess + ask), 3) if assess + ask else None,
                    "useful_share": round(useful / ratings, 3) if ratings else None,
                    "citations_flagged": flagged})
    return out


def main() -> None:
    rows = weekly()
    if not rows:
        print("no responses logged yet")
        return
    fmt = lambda v: "–" if v is None else f"{v:.0%}" if isinstance(v, float) else str(v)  # noqa: E731
    print("week       assess  ask  ask refused  rated  useful  citations flagged")
    for r in rows:
        print(f"{r['week']:9s}  {r['assess']:6d}  {r['ask']:3d}  {fmt(r['ask_refusal_rate']):>11s}  "
              f"{fmt(r['rated_share']):>5s}  {fmt(r['useful_share']):>6s}  {r['citations_flagged']:17d}")
    print("Not measurable from the logs yet (see docs/pilot-plan.md): active users (no user id is logged), "
          "predicted vs actual award time (an assessment is not linked to the tender it planned), response time.")


if __name__ == "__main__":
    main()
