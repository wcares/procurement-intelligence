"""What changed recently, for the home dashboard: source changes the pipeline detected (procintel.pipeline event log),
counted by kind over the last few days, in planner words. Pipeline bookkeeping (data rebuilt, passages re-cut) is left
out; the Event log page (admins) has every event and what it triggered.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from procintel.pipeline import store

DAYS = 14
SAMPLE = 3   # example keys per kind
LABELS = {   # event type -> what it means to a planner; types not listed are bookkeeping
    "Notice.added": "new procurement notices",
    "Notice.changed": "procurement notices updated",
    "ContractAward.added": "contract awards signed",
    "ContractAward.changed": "contract awards corrected",
    "Project.added": "projects now tracked",
    "Project.changed": "projects with changed details (status, dates, financing)",
    "Document.added": "completion reports added",
    "Document.changed": "completion reports revised",
    "SupervisionDoc.added": "supervision reports and restructuring papers added",
    "SupervisionDoc.changed": "supervision reports and restructuring papers revised",
    "Indicator.added": "governance scores added",
    "Indicator.changed": "governance scores revised",
}


def recent(days: int = DAYS, db_path: Path | None = None, now: datetime | None = None) -> dict:
    """{days, since, items: [{type, label, count, last, examples}], total}, most recent kind first."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    since = now - timedelta(days=days)
    con = store.connect(db_path)
    try:
        rows = con.execute("""SELECT type, count(*), max(detected_at), list(key ORDER BY detected_at DESC)[1:?]
                              FROM event_log WHERE detected_at >= ? GROUP BY 1""", [SAMPLE, since]).fetchall()
    finally:
        con.close()
    items = [{"type": t, "label": LABELS[t], "count": int(n), "last": last.isoformat() + "Z", "examples": list(ex)}
             for t, n, last, ex in rows if t in LABELS]
    items.sort(key=lambda i: i["last"], reverse=True)
    return {"days": days, "since": since.isoformat() + "Z", "items": items, "total": sum(i["count"] for i in items)}
