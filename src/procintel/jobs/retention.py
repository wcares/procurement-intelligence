"""Retention (docs/event-pipeline-design.md 6d): what is kept, and for how long. A daily background job applies it.

Each target removes what is past its age and returns how many items that was; with dry=True it only counts. Kept
RETENTION_DAYS (default 30, a setting): the pipeline's event history (not the entity state, which is current data),
finished background jobs, the HTTP cache (re-fetched when needed), refresh logs, shadow builds that were never
promoted and the __previous tables a promotion left behind. The response log and feedback are kept RETENTION_DAYS too,
except while a pilot runs (PILOT_UNTIL, a date): then nothing is removed from them until that date has passed. Derived
knowledge in use (tables, passages, vectors, models) and evaluation labels are not touched.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from procintel.core import db, paths

RETENTION_DAYS = int(os.environ.get("PROCINTEL_RETENTION_DAYS", "30"))
PILOT_UNTIL = os.environ.get("PROCINTEL_PILOT_UNTIL", "")  # YYYY-MM-DD while a pilot runs, else empty


@dataclass(frozen=True)
class Target:
    name: str
    label: str
    purge: Callable[[datetime, bool], int]   # (cutoff, dry) -> items removed (or that would be)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _rows(path, table: str, where: str, args: list, dry: bool) -> int:
    if not path.exists():
        return 0
    con = db.connect(path)
    try:
        if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = ?", [table]).fetchone():
            return 0
        n = con.execute(f"SELECT count(*) FROM {table} WHERE {where}", args).fetchone()[0]
        if n and not dry:
            con.execute(f"DELETE FROM {table} WHERE {where}", args)
        return n
    finally:
        con.close()


def pipeline_history(cutoff: datetime, dry: bool) -> int:
    return sum(_rows(paths.PIPELINE_DB, t, f"{c} < ?", [cutoff], dry) for t, c in
               (("event_log", "detected_at"), ("firing", "fired_at"), ("detection", "ran_at"), ("action_run", "ran_at")))


def alerts(cutoff: datetime, dry: bool) -> int:
    return _rows(paths.PIPELINE_DB, "alert", "created_at < ?", [cutoff], dry)


def finished_jobs(cutoff: datetime, dry: bool) -> int:
    return _rows(paths.JOBS_DB, "jobs", "status IN ('done', 'failed') AND coalesce(finished_at, created_at) < ?",
                 [cutoff], dry)


def pilot_running(today: date | None = None) -> bool:
    return bool(PILOT_UNTIL) and (today or date.today()) <= date.fromisoformat(PILOT_UNTIL)


def responses(cutoff: datetime, dry: bool) -> int:
    if pilot_running():
        return 0  # the pilot's KPIs span its whole length
    feedback_rows = _rows(paths.FEEDBACK_DB, "feedback", "created_at < ?", [cutoff], dry)
    return feedback_rows + _rows(paths.FEEDBACK_DB, "response_log", "created_at < ?", [cutoff], dry)


def _files(folder, cutoff: datetime, dry: bool) -> int:
    if not folder.exists():
        return 0
    limit = cutoff.replace(tzinfo=timezone.utc).timestamp()
    n = 0
    for f in folder.iterdir():
        if f.is_file() and f.stat().st_mtime < limit:
            n += 1
            if not dry:
                f.unlink()
    return n


def http_cache(cutoff: datetime, dry: bool) -> int:
    """Cached World Bank responses, wherever they are kept (procintel.core.blob: data folder or object storage)."""
    from procintel.core import blob
    from procintel.ingestion.wb_client import CACHE_PREFIX
    old = [k for k, modified in blob.store().list(CACHE_PREFIX) if modified < cutoff]
    if not dry:
        for k in old:
            blob.store().delete(k)
    return len(old)


def refresh_logs(cutoff: datetime, dry: bool) -> int:
    return _files(paths.LOG_DIR, cutoff, dry)


def old_shadows(cutoff: datetime, dry: bool) -> int:
    """Shadow builds not promoted, built before the cutoff (their tables dropped, state 'expired'), and the __previous
    tables of promotions before the cutoff. Counts tables."""
    from procintel.learning import shadows
    n = 0
    for s in shadows.states():
        built = datetime.fromisoformat(s["built_at"].rstrip("Z")) if s.get("built_at") else None
        if s["status"] in ("built", "evaluated") and built and built < cutoff and s["name"] in shadows.SHADOWS:
            n += len(shadows.SHADOWS[s["name"]].tables) + 1
            if not dry:
                shadows.discard(s["name"])
                shadows.set_state(s["name"], status="expired", note=f"not promoted within {RETENTION_DAYS} days")
        promoted = s.get("promoted_at")
        if s["status"] == "promoted" and promoted and datetime.fromisoformat(promoted.rstrip("Z")) < cutoff:
            con = db.connect()
            try:
                for t in shadows.SHADOWS[s["name"]].tables:
                    if con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = ?",
                                   [f"{t}__previous"]).fetchone():
                        n += 1
                        if not dry:
                            con.execute(f"DROP TABLE {t}__previous")
            finally:
                con.close()
    return n


TARGETS = [
    Target("pipeline_history", "Change-detection history (events, rule firings, runs)", pipeline_history),
    Target("alerts", "Planners' alerts", alerts),
    Target("finished_jobs", "Finished background jobs", finished_jobs),
    Target("responses", "Response log and feedback (kept while a pilot runs)", responses),
    Target("http_cache", "Cached World Bank API responses", http_cache),
    Target("refresh_logs", "Refresh logs", refresh_logs),
    Target("old_shadows", "Unpromoted shadow builds and superseded tables", old_shadows),
]


def apply(dry: bool = False, now: datetime | None = None) -> dict:
    """{target: items removed (or that would be, with dry)} for everything older than RETENTION_DAYS."""
    cutoff = (now or _now()) - timedelta(days=RETENTION_DAYS)
    started = time.time()
    out = {t.name: t.purge(cutoff, dry) for t in TARGETS}
    return {"dry": dry, "cutoff": cutoff.isoformat() + "Z", "pilot_until": PILOT_UNTIL or None, "removed": out,
            "seconds": round(time.time() - started, 1)}


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(apply(dry="--apply" not in sys.argv), indent=1))
