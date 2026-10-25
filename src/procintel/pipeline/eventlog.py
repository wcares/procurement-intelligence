"""The event log for the Event log page: batches newest first, each with its events, the rules they fired, the job
those queued (and its state) and the actions that ran. Filter by entity type ("Notice") or event type
("Notice.changed"); derived events (Data.updated, ...) are shown with their batch but never match a filter on their own.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from procintel.jobs import store as jobs_store
from procintel.pipeline import store

EVENTS_PER_BATCH = 100


def _iso(t: datetime) -> str:
    return t.isoformat() + "Z"


def batches(type_filter: str | None = None, limit: int = 20, before: str | None = None,
            db_path: Path | None = None, jobs_db: Path | None = None) -> dict:
    con = store.connect(db_path)
    try:
        where, args = [], []
        if type_filter:
            where.append("(type = ? OR type LIKE ?)")
            args += [type_filter, type_filter + ".%"]
        if before:
            where.append("detected_at < ?")
            args.append(datetime.fromisoformat(before.rstrip("Z")))
        sql = ("SELECT batch_id, max(detected_at) AS last_at FROM event_log"
               + (" WHERE " + " AND ".join(where) if where else "") + " GROUP BY 1 ORDER BY last_at DESC LIMIT ?")
        ids = con.execute(sql, args + [limit]).fetchall()
        out = []
        for batch, at in ids:
            counts = dict(con.execute("SELECT type, count(*) FROM event_log WHERE batch_id = ? GROUP BY 1 ORDER BY 1",
                                      [batch]).fetchall())
            ev_sql = "SELECT type, key, changed_fields, detected_at FROM event_log WHERE batch_id = ?"
            ev_args: list = [batch]
            if type_filter:
                ev_sql += " AND (type = ? OR type LIKE ?)"
                ev_args += [type_filter, type_filter + ".%"]
            events = [{"type": t, "key": k, "changed": json.loads(c), "at": _iso(d)} for t, k, c, d in con.execute(
                ev_sql + " ORDER BY detected_at, type, key LIMIT ?", ev_args + [EVENTS_PER_BATCH]).fetchall()]
            firings = [{"rule": r, "events": n, "actions": json.loads(a), "job": j, "at": _iso(f)}
                       for r, n, a, j, f in con.execute("SELECT rule_id, events, actions, job_id, fired_at FROM firing "
                                                        "WHERE batch_id = ? ORDER BY rule_id", [batch]).fetchall()]
            ran = [{"action": a, "outcome": o, "at": _iso(t)} for a, o, t in con.execute(
                "SELECT action, outcome, ran_at FROM action_run WHERE batch_id = ? ORDER BY ran_at", [batch]).fetchall()]
            out.append({"batch": batch, "at": _iso(at), "counts": counts, "events": events, "firings": firings,
                        "actionsRun": ran})
        types = [t for (t,) in con.execute("SELECT DISTINCT type FROM event_log ORDER BY 1").fetchall()]
    finally:
        con.close()
    jobs = jobs_store.statuses(sorted({f["job"] for b in out for f in b["firings"] if f["job"]}), jobs_db)
    for b in out:
        for f in b["firings"]:
            f["jobStatus"] = jobs.get(f["job"]) if f["job"] else None
    return {"batches": out, "types": types, "more": len(out) == limit}
