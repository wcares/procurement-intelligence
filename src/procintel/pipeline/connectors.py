"""Connector status for the Connectors page, and when each source is next read (its interval and on/off come from
procintel.pipeline.connector_config).

Every tracked entity type is read by one connector (EntityType.source, .mode). A read that fails is logged with its
error (store.log_detection) and does not stop the other sources; the failing source then backs off: after n failures
in a row it waits its interval times 2^(n-1), at most a day (or its interval when that is longer).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from procintel.pipeline import connector_config, entities, store, webhook

BACKOFF_CAP = timedelta(days=1)
HISTORY = 20   # reads per source looked at for the failure count


def wait(et: entities.EntityType, failures: int) -> timedelta:
    every = connector_config.every(et)      # the configured interval (procintel.pipeline.connector_config)
    if failures <= 1:
        return every
    return min(every * 2 ** (failures - 1), max(every, BACKOFF_CAP))


def _reads(name: str, db_path: Path | None) -> list[tuple]:
    con = store.connect(db_path)
    try:
        return con.execute("SELECT ran_at, items, events, note, error FROM detection WHERE entity_type = ? "
                           "ORDER BY ran_at DESC LIMIT ?", [name, HISTORY]).fetchall()
    finally:
        con.close()


def _failures(reads: list[tuple]) -> int:
    n = 0
    for r in reads:
        if not r[4]:
            break
        n += 1
    return n


def due(et: entities.EntityType, force: bool, db_path: Path | None = None) -> bool:
    if force:
        return True
    if not connector_config.enabled(et.name):
        return False
    reads = _reads(et.name, db_path)
    return not reads or entities.now() - reads[0][0] >= wait(et, _failures(reads))


def cursor(name: str, db_path: Path | None = None) -> str:
    """What the next read asks for, in words."""
    con = store.connect(db_path)
    try:
        if name == "Notice":
            newest = con.execute("SELECT max(json_extract_string(fields, '$.notice_date')) FROM entity_state "
                                 "WHERE entity_type = 'Notice'").fetchone()[0]
            return (f"notices newest first, back to {entities.NOTICE_WINDOW.days} days before the newest known "
                    f"({newest[:10]})") if newest else "not started"
        if name == "Document":
            n = con.execute("SELECT count(*) FROM entity_state WHERE entity_type = 'Document'").fetchone()[0]
            return f"reports newest first until all {n} tracked ones are seen (the newest {entities.DOCUMENT_SCOPE} are in scope)"
        return "full read each time, compared with the stored state"
    finally:
        con.close()


def words(d: timedelta) -> str:
    """1 hour, 6 hours, 1 day, 7 days."""
    h = d.total_seconds() / 3600
    n, unit = (h / 24, "day") if h >= 24 and h % 24 == 0 else (h, "hour") if h >= 1 else (h * 60, "minute")
    n = int(n) if n == int(n) else round(n, 1)
    return f"{n} {unit}{'' if n == 1 else 's'}"


def _iso(t: datetime | None) -> str | None:
    return t.isoformat() + "Z" if t else None


def status(db_path: Path | None = None) -> list[dict]:
    out = []
    for et in entities.ENTITY_TYPES.values():
        reads = _reads(et.name, db_path)
        ok = next((r for r in reads if not r[4]), None)
        bad = next((r for r in reads if r[4]), None)
        failures = _failures(reads)
        cfg = connector_config.settings(et.name)
        out.append({
            "name": et.name, "source": et.source, "mode": cfg["mode"], "every": words(connector_config.every(et)),
            "settings": cfg, "defaults": connector_config.defaults(et.name),
            "customised": connector_config.customised(et.name),
            "push": {"path": f"/connectors/{et.name}/webhook", "secretSet": webhook.secret(et.name) is not None,
                     "secretVar": f"PROCINTEL_WEBHOOK_SECRET_{et.name.upper()}"},
            "cursor": cursor(et.name, db_path),
            "lastRead": _iso(reads[0][0]) if reads else None,
            "lastSuccess": {"at": _iso(ok[0]), "items": ok[1], "events": ok[2], "note": ok[3]} if ok else None,
            "lastError": {"at": _iso(bad[0]), "message": bad[4]} if bad else None,
            "failures": failures,
            "nextRead": _iso(reads[0][0] + wait(et, failures)) if reads else None,
            "due": cfg["enabled"] and (not reads or entities.now() >= reads[0][0] + wait(et, failures)),
        })
    return out
