"""Persistent job queue in its own DuckDB file (data/jobs.duckdb), so pending and paused jobs survive a restart.

Each call opens and closes its connection (like procintel.feedback), so a command-line tool can queue a job while the
backend runs. A job moves pending -> running -> done | failed; a job paused between steps goes back to pending with its
cursor, and resumes from there.

With Postgres (procintel.db) several worker processes share the queue: a job is claimed in one Postgres statement
(FOR UPDATE SKIP LOCKED), so no two workers take the same job, and every step writes a heartbeat, so a worker that
starts only takes back jobs whose worker stopped (no heartbeat for STALE). Table meta holds what the api and the
workers share: the time of the last user request (workers wait for idle time) and a data version that a worker raises
after changing data (each api reloads when it sees it change).
"""
from __future__ import annotations

import json
import random
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from procintel import db, paths

DB_PATH = paths.JOBS_DB
MAX_ATTEMPTS = 3
STALE = timedelta(minutes=30)  # longer than any single step (a refresh with fetching is one step of a few minutes)
_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# JSON is kept as text (VARCHAR): Postgres will not take the text the postgres extension sends when it updates a json
# column; values are encoded and decoded here.
def _connect(db_path: Path | None) -> duckdb.DuckDBPyConnection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id VARCHAR PRIMARY KEY, kind VARCHAR, params VARCHAR, reason VARCHAR, status VARCHAR, created_at TIMESTAMP,
        started_at TIMESTAMP, finished_at TIMESTAMP, cursor VARCHAR, result VARCHAR, error VARCHAR, attempts INTEGER,
        steps INTEGER)""")
    con.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS worker VARCHAR")
    con.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
    return con


def _shared(db_path: Path | None) -> bool:
    """True when the queue lives in Postgres, where several processes may use it at once."""
    return db.backend() == "postgres" and (db_path or DB_PATH) == paths.JOBS_DB


def _row(cols: list[str], r: tuple) -> dict:
    d = dict(zip(cols, r))
    for k in ("params", "cursor", "result"):
        d[k] = json.loads(d[k]) if d[k] is not None else None
    for k in ("created_at", "started_at", "finished_at"):
        d[k] = d[k].isoformat() + "Z" if d[k] else None
    return d


def enqueue(kind: str, reason: str, params: dict | None = None, dedupe: bool = True, db_path: Path | None = None) -> str | None:
    """Add a job; with dedupe, nothing is added when a job of the same kind is already pending or running (None)."""
    with _LOCK:
        con = _connect(db_path)
        try:
            if dedupe and con.execute("SELECT 1 FROM jobs WHERE kind = ? AND status IN ('pending', 'running')",
                                      [kind]).fetchone():
                return None
            jid = uuid.uuid4().hex[:12]
            con.execute("INSERT INTO jobs (id, kind, params, reason, status, created_at, attempts, steps) "
                        "VALUES (?, ?, ?, ?, 'pending', ?, 0, 0)",
                        [jid, kind, json.dumps(params or {}), reason, _now()])
            return jid
        finally:
            con.close()


_CLAIM = """UPDATE jobs.jobs SET status = 'running', worker = '{w}', started_at = coalesce(started_at, now() at time zone 'utc'),
    heartbeat_at = now() at time zone 'utc'
    WHERE id = (SELECT id FROM jobs.jobs WHERE status = 'pending' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
    RETURNING id"""


def _claim(con: duckdb.DuckDBPyConnection, sql: str, tries: int = 8) -> tuple | None:
    """Run the claim in its own transaction (without one the update is not committed). The postgres extension reads
    at repeatable read, so a worker that collides with another's claim gets a serialization error: nothing was
    claimed twice, it rolls back and tries again."""
    for attempt in range(tries):
        con.execute("BEGIN")
        try:
            r = con.execute(f"SELECT * FROM postgres_query('pg', '{sql}')").fetchone()
            con.execute("COMMIT")
            return r
        except duckdb.IOException as e:
            con.execute("ROLLBACK")
            if "could not serialize" not in str(e) or attempt == tries - 1:
                raise
            time.sleep(0.05 * (attempt + 1) * random.random())
    return None


def next_pending(db_path: Path | None = None, worker: str = "local") -> dict | None:
    """The oldest pending job, marked running by this worker (claimed atomically when the queue is shared)."""
    with _LOCK:
        con = _connect(db_path)
        try:
            if _shared(db_path):
                sql = _CLAIM.format(w=worker.replace("'", "")).replace("'", "''")
                r = _claim(con, sql)
                if r is None:
                    return None
                q = con.execute("SELECT * FROM jobs WHERE id = ?", [r[0]])
                return _row([d[0] for d in q.description], q.fetchone())
            q = con.execute("SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1")
            r = q.fetchone()
            if r is None:
                return None
            job = _row([d[0] for d in q.description], r)
            con.execute("UPDATE jobs SET status = 'running', worker = ?, started_at = coalesce(started_at, ?), "
                        "heartbeat_at = ? WHERE id = ?", [worker, _now(), _now(), job["id"]])
            return job | {"status": "running", "worker": worker}
        finally:
            con.close()


def _update(jid: str, sql: str, params: list, db_path: Path | None) -> None:
    with _LOCK:
        con = _connect(db_path)
        try:
            con.execute(f"UPDATE jobs SET {sql} WHERE id = ?", params + [jid])
        finally:
            con.close()


def checkpoint(jid: str, cursor: dict, db_path: Path | None = None) -> None:
    _update(jid, "cursor = ?, steps = steps + 1, heartbeat_at = ?", [json.dumps(cursor), _now()], db_path)


def pause(jid: str, db_path: Path | None = None) -> None:
    _update(jid, "status = 'pending'", [], db_path)


def finish(jid: str, result: dict, db_path: Path | None = None) -> None:
    _update(jid, "status = 'done', finished_at = ?, result = ?", [_now(), json.dumps(result)], db_path)


def fail(jid: str, error: str, db_path: Path | None = None) -> str:
    """Retried from its last cursor up to MAX_ATTEMPTS times, then failed; returns the new status."""
    with _LOCK:
        con = _connect(db_path)
        try:
            n = con.execute("SELECT attempts + 1 FROM jobs WHERE id = ?", [jid]).fetchone()[0]
            status = "failed" if n >= MAX_ATTEMPTS else "pending"
            con.execute("UPDATE jobs SET attempts = ?, status = ?, error = ?, finished_at = ? WHERE id = ?",
                        [n, status, error[:500], _now() if status == "failed" else None, jid])
            return status
        finally:
            con.close()


def recover(db_path: Path | None = None, stale_only: bool = False) -> int:
    """At startup: jobs left running by a stopped worker go back to pending (they resume from their cursor). With
    several workers (stale_only) only jobs without a heartbeat for STALE: the others belong to live workers."""
    cond = "status = 'running'" + (" AND coalesce(heartbeat_at, started_at) < ?" if stale_only else "")
    args = [_now() - STALE] if stale_only else []
    with _LOCK:
        con = _connect(db_path)
        try:
            n = con.execute(f"SELECT count(*) FROM jobs WHERE {cond}", args).fetchone()[0]
            con.execute(f"UPDATE jobs SET status = 'pending' WHERE {cond}", args)
            return n
        finally:
            con.close()


def set_meta(key: str, value: str, db_path: Path | None = None) -> None:
    with _LOCK:
        con = _connect(db_path)
        try:
            con.execute("DELETE FROM meta WHERE key = ?", [key])
            con.execute("INSERT INTO meta VALUES (?, ?)", [key, value])
        finally:
            con.close()


def get_meta(key: str, db_path: Path | None = None) -> str | None:
    con = _connect(db_path)
    try:
        r = con.execute("SELECT value FROM meta WHERE key = ?", [key]).fetchone()
        return r[0] if r else None
    finally:
        con.close()


def touch_activity(db_path: Path | None = None) -> None:
    set_meta("last_request", _now().isoformat(), db_path)


def last_activity(db_path: Path | None = None) -> datetime | None:
    v = get_meta("last_request", db_path)
    return datetime.fromisoformat(v) if v else None


def bump_version(db_path: Path | None = None) -> str:
    """Called by a worker after it changed the data; every api reloads when it sees a new value."""
    v = uuid.uuid4().hex[:12]
    set_meta("data_version", v, db_path)
    return v


def data_version(db_path: Path | None = None) -> str | None:
    return get_meta("data_version", db_path)


def last_done(kind: str, db_path: Path | None = None) -> datetime | None:
    con = _connect(db_path)
    try:
        r = con.execute("SELECT max(finished_at) FROM jobs WHERE kind = ? AND status = 'done'", [kind]).fetchone()
        return r[0]
    finally:
        con.close()


def due(kind: str, every: timedelta, db_path: Path | None = None) -> bool:
    """True when no job of this kind finished within `every` (used for the daily drift check)."""
    last = last_done(kind, db_path)
    return last is None or _now() - last >= every


def recent(limit: int = 30, db_path: Path | None = None) -> list[dict]:
    con = _connect(db_path)
    try:
        q = con.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", [limit])
        cols = [d[0] for d in q.description]
        return [_row(cols, r) for r in q.fetchall()]
    finally:
        con.close()
