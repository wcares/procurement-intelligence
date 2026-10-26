"""State of every tracked entity and the log of what changed (data/pipeline.duckdb; the worker is its only writer).

entity_state  one row per entity: its key, a fingerprint of the watched fields, the fields themselves, when first and
              last seen
event_log     one row per change: <Type>.added / .changed / .removed, the key, the changed fields, old and new values
              (new holds the full source row, which the actions apply), the detection batch
firing        one row per rule that matched in a batch: how many events, the actions it asked for, the job queued
detection     one row per entity type and run: when, how many items read, events, or the error
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from procintel.core import db, paths


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = db_path or paths.PIPELINE_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS entity_state (entity_type VARCHAR, key VARCHAR, fingerprint VARCHAR,
                   fields VARCHAR, first_seen TIMESTAMP, last_seen TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS event_log (event_id VARCHAR, batch_id VARCHAR, type VARCHAR, key VARCHAR,
                   changed_fields VARCHAR, old VARCHAR, new VARCHAR, detected_at TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS firing (batch_id VARCHAR, rule_id VARCHAR, events INTEGER, actions VARCHAR,
                   job_id VARCHAR, fired_at TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS detection (batch_id VARCHAR, entity_type VARCHAR, ran_at TIMESTAMP,
                   items INTEGER, events INTEGER, note VARCHAR)""")
    con.execute("ALTER TABLE detection ADD COLUMN IF NOT EXISTS error VARCHAR")   # older stores lack it
    con.execute("""CREATE TABLE IF NOT EXISTS action_run (batch_id VARCHAR, action VARCHAR, ran_at TIMESTAMP,
                   outcome VARCHAR)""")
    return con


def norm(v):
    """A value as the fingerprint sees it."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (list, tuple)) or hasattr(v, "tolist") and not isinstance(v, (str, pd.Timestamp)):
        v = list(v.tolist() if hasattr(v, "tolist") else v)
    if v is pd.NaT:
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        if pd.isna(v):
            return None
        ts = pd.Timestamp(v)
        if ts.tzinfo is None and ts == ts.normalize():  # a DATE column read through pandas: a midnight timestamp
            return ts.date().isoformat()
        return (ts.tz_convert("UTC") if ts.tzinfo else ts).strftime("%Y-%m-%dT%H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):  # pandas reads a whole-number column with gaps as floats: 0.0 and 0 are the same value
        return int(v) if v.is_integer() else round(v, 4)
    if hasattr(v, "item") and not isinstance(v, str):  # numpy scalars
        return norm(v.item())
    if isinstance(v, str) and v[:1] == "[":
        try:
            return json.dumps(sorted(json.loads(v), key=json.dumps), sort_keys=True)
        except ValueError:
            return v
    if isinstance(v, list):
        return json.dumps(sorted(v, key=lambda x: json.dumps(x, default=str)), sort_keys=True, default=str)
    return v


def watched_fields(row: dict, watched: list[str]) -> dict:
    return {f: norm(row.get(f)) for f in watched}


def fingerprint(fields: dict) -> str:
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()[:16]


def new_batch() -> str:
    return _now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def states(entity_type: str, db_path: Path | None = None) -> dict[str, tuple[str, dict]]:
    con = connect(db_path)
    try:
        return {k: (fp, json.loads(f)) for k, fp, f in con.execute(
            "SELECT key, fingerprint, fields FROM entity_state WHERE entity_type = ?", [entity_type]).fetchall()}
    finally:
        con.close()


def diff(entity_type: str, watched: list[str], rows: dict[str, dict], known: dict[str, tuple[str, dict]],
         complete: bool) -> list[dict]:
    """Events for the source rows against the known state. Removals only when the source read was complete (a
    newest-first read of notices covers a window, so absence there means nothing)."""
    out = []
    for key, row in rows.items():
        fields = watched_fields(row, watched)
        fp = fingerprint(fields)
        if key not in known:
            out.append({"type": f"{entity_type}.added", "key": key, "changed": [], "old": None, "new": row,
                        "fields": fields, "fp": fp})
        elif known[key][0] != fp:
            old = known[key][1]
            changed = [f for f in watched if str(old.get(f)) != str(fields[f])]
            out.append({"type": f"{entity_type}.changed", "key": key, "changed": changed, "old": old, "new": row,
                        "fields": fields, "fp": fp})
    if complete:
        for key in set(known) - set(rows):
            out.append({"type": f"{entity_type}.removed", "key": key, "changed": [], "old": known[key][1], "new": None,
                        "fields": None, "fp": None})
    return out


def _clean(row):
    """A source row for the event log: missing dates and numbers (pandas NaT, float NaN) as JSON null; str() of NaT
    would write the text "NaT", which the actions then cannot write back as a date."""
    if not isinstance(row, dict):
        return row
    return {k: (None if v is pd.NaT or (isinstance(v, float) and math.isnan(v)) else v) for k, v in row.items()}


def record(entity_type: str, batch_id: str, events: list[dict], seen: list[str], db_path: Path | None = None) -> None:
    """Write the events, then bring the state up to date (new and changed fingerprints, removals, last_seen)."""
    now = _now()
    con = connect(db_path)
    try:
        if events:  # executemany refuses an empty list
            con.executemany("INSERT INTO event_log VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (uuid.uuid4().hex[:12], batch_id, e["type"], e["key"], json.dumps(e["changed"]),
                 json.dumps(_clean(e["old"]), default=str), json.dumps(_clean(e["new"]), default=str), now)
                for e in events])
        for e in events:
            if e["type"].endswith(".removed"):
                con.execute("DELETE FROM entity_state WHERE entity_type = ? AND key = ?", [entity_type, e["key"]])
            elif e["type"].endswith(".added"):
                con.execute("INSERT INTO entity_state VALUES (?, ?, ?, ?, ?, ?)",
                            [entity_type, e["key"], e["fp"], json.dumps(e["fields"], default=str), now, now])
            else:
                con.execute("UPDATE entity_state SET fingerprint = ?, fields = ?, last_seen = ? "
                            "WHERE entity_type = ? AND key = ?",
                            [e["fp"], json.dumps(e["fields"], default=str), now, entity_type, e["key"]])
        if seen:
            con.execute("UPDATE entity_state SET last_seen = ? WHERE entity_type = ? AND key IN (SELECT unnest(?))",
                        [now, entity_type, seen])
    finally:
        con.close()


def log_derived(batch_id: str, events: list[dict], db_path: Path | None = None) -> None:
    """Events an action reported (Package.award_changed, Data.updated), so the log shows what each change led to."""
    if not events:
        return
    con = connect(db_path)
    try:
        con.executemany("INSERT INTO event_log VALUES (?, ?, ?, ?, '[]', 'null', 'null', ?)",
                        [(uuid.uuid4().hex[:12], batch_id, e["type"], e["key"], _now()) for e in events])
    finally:
        con.close()


def log_action(batch_id: str, action: str, outcome: str, db_path: Path | None = None) -> None:
    con = connect(db_path)
    try:
        con.execute("INSERT INTO action_run VALUES (?, ?, ?, ?)", [batch_id, action, _now(), outcome])
    finally:
        con.close()


def hours_since_action(action: str, db_path: Path | None = None) -> float | None:
    con = connect(db_path)
    try:
        r = con.execute("SELECT max(ran_at) FROM action_run WHERE action = ? AND outcome = 'ran'", [action]).fetchone()
        return None if r[0] is None else (_now() - r[0]).total_seconds() / 3600
    finally:
        con.close()


def recent_batches(since: datetime, db_path: Path | None = None) -> dict[str, list[dict]]:
    """Events since a time, grouped by batch (for a dry run of rules)."""
    con = connect(db_path)
    try:
        out: dict[str, list[dict]] = {}
        for b, t, k, c in con.execute("SELECT batch_id, type, key, changed_fields FROM event_log WHERE detected_at >= ? "
                                      "ORDER BY detected_at", [since]).fetchall():
            out.setdefault(b, []).append({"type": t, "key": k, "changed": json.loads(c)})
        return out
    finally:
        con.close()


def seed(entity_type: str, watched: list[str], rows: dict[str, dict], db_path: Path | None = None) -> int:
    """Start tracking a type from what the database already holds, without events (its first detection run)."""
    now = _now()
    if not rows:
        return 0
    con = connect(db_path)
    try:
        con.executemany("INSERT INTO entity_state VALUES (?, ?, ?, ?, ?, ?)", [
            (entity_type, k, fingerprint(watched_fields(r, watched)),
             json.dumps(watched_fields(r, watched), default=str), now, now) for k, r in rows.items()])
        return len(rows)
    finally:
        con.close()


def log_detection(batch_id: str, entity_type: str, items: int, events: int, note: str = "",
                  db_path: Path | None = None, error: str | None = None) -> None:
    """One source read; `error` set when reading failed (nothing was recorded for that type then)."""
    con = connect(db_path)
    try:
        con.execute("INSERT INTO detection (batch_id, entity_type, ran_at, items, events, note, error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)", [batch_id, entity_type, _now(), items, events, note, error])
    finally:
        con.close()


def log_firing(batch_id: str, rule_id: str, events: int, actions: list[str], job_id: str | None,
               db_path: Path | None = None) -> None:
    con = connect(db_path)
    try:
        con.execute("INSERT INTO firing VALUES (?, ?, ?, ?, ?, ?)",
                    [batch_id, rule_id, events, json.dumps(actions), job_id, _now()])
    finally:
        con.close()


def batch_events(batch_id: str, types: list[str] | None = None, db_path: Path | None = None) -> list[dict]:
    con = connect(db_path)
    try:
        q = "SELECT type, key, changed_fields, new FROM event_log WHERE batch_id = ?"
        args: list = [batch_id]
        if types:
            q += " AND type IN (SELECT unnest(?))"
            args.append(types)
        return [{"type": t, "key": k, "changed": json.loads(c), "new": json.loads(n)}
                for t, k, c, n in con.execute(q, args).fetchall()]
    finally:
        con.close()


def overview(limit: int = 50, db_path: Path | None = None) -> dict:
    """For the Settings page: tracked items per type with the last run, recent events, recent rule firings."""
    con = connect(db_path)
    try:
        tracked = dict(con.execute("SELECT entity_type, count(*) FROM entity_state GROUP BY 1").fetchall())
        runs = con.execute("""SELECT entity_type, ran_at, items, events, note FROM detection
                              QUALIFY row_number() OVER (PARTITION BY entity_type ORDER BY ran_at DESC) = 1""").fetchall()
        last = {t: {"ranAt": r.isoformat() + "Z", "items": i, "events": e, "note": n} for t, r, i, e, n in runs}
        events = [{"type": t, "key": k, "changed": json.loads(c), "detectedAt": d.isoformat() + "Z", "batch": b}
                  for t, k, c, d, b in con.execute(
                      "SELECT type, key, changed_fields, detected_at, batch_id FROM event_log "
                      "ORDER BY detected_at DESC LIMIT ?", [limit]).fetchall()]
        firings = [{"batch": b, "rule": r, "events": n, "actions": json.loads(a), "job": j, "firedAt": f.isoformat() + "Z"}
                   for b, r, n, a, j, f in con.execute(
                       "SELECT * FROM firing ORDER BY fired_at DESC LIMIT ?", [limit]).fetchall()]
        return {"tracked": tracked, "lastRun": last, "events": events, "firings": firings}
    finally:
        con.close()
