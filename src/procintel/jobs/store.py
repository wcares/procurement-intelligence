"""Persistent job queue in its own DuckDB file (data/jobs.duckdb), so pending and paused jobs survive a restart.

Each call opens and closes its connection (like procintel.feedback), so a command-line tool can queue a job while the
backend runs. A job moves pending -> running -> done | failed; a job paused between steps goes back to pending with its
cursor, and resumes from there.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from procintel import db, paths

DB_PATH = paths.JOBS_DB
MAX_ATTEMPTS = 3
_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _connect(db_path: Path | None) -> duckdb.DuckDBPyConnection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id VARCHAR PRIMARY KEY, kind VARCHAR, params JSON, reason VARCHAR, status VARCHAR, created_at TIMESTAMP,
        started_at TIMESTAMP, finished_at TIMESTAMP, cursor JSON, result JSON, error VARCHAR, attempts INTEGER,
        steps INTEGER)""")
    return con


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
            con.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, 'pending', ?, NULL, NULL, NULL, NULL, NULL, 0, 0)",
                        [jid, kind, json.dumps(params or {}), reason, _now()])
            return jid
        finally:
            con.close()


def next_pending(db_path: Path | None = None) -> dict | None:
    """The oldest pending job, marked running."""
    with _LOCK:
        con = _connect(db_path)
        try:
            q = con.execute("SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1")
            r = q.fetchone()
            if r is None:
                return None
            job = _row([d[0] for d in q.description], r)
            con.execute("UPDATE jobs SET status = 'running', started_at = coalesce(started_at, ?) WHERE id = ?",
                        [_now(), job["id"]])
            return job | {"status": "running"}
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
    _update(jid, "cursor = ?, steps = steps + 1", [json.dumps(cursor)], db_path)


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


def recover(db_path: Path | None = None) -> int:
    """At startup: jobs left running by a stopped backend go back to pending (they resume from their cursor)."""
    with _LOCK:
        con = _connect(db_path)
        try:
            n = con.execute("SELECT count(*) FROM jobs WHERE status = 'running'").fetchone()[0]
            con.execute("UPDATE jobs SET status = 'pending' WHERE status = 'running'")
            return n
        finally:
            con.close()


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
