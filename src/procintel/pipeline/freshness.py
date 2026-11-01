"""How current the data behind a number is: when each source was last read without an error, and how often it is read.

Planners see this next to forecasts and answers ("notices read 2 h ago"), so a number from stale data is visible as such.
A source counts as late when its last good read is older than twice its interval.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from procintel.pipeline import store
from procintel.pipeline.entities import ENTITY_TYPES

LABELS = {"Notice": "procurement notices", "Project": "projects", "Document": "completion reports",
          "SupervisionDoc": "status reports and restructuring papers", "ContractAward": "contract awards",
          "Indicator": "governance indicators"}


def sources(db_path: Path | None = None, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    con = store.connect(db_path)
    try:
        last = dict(con.execute("SELECT entity_type, max(ran_at) FROM detection WHERE error IS NULL GROUP BY 1").fetchall())
    finally:
        con.close()
    out = []
    for name, e in ENTITY_TYPES.items():
        at = last.get(name)
        hours = round((now - at).total_seconds() / 3600, 1) if at else None
        every = e.every.total_seconds() / 3600
        out.append({"entity": name, "label": LABELS.get(name, name), "lastRead": at.isoformat() + "Z" if at else None,
                    "hoursAgo": hours, "everyHours": every, "late": hours is None or hours > 2 * every})
    return out
