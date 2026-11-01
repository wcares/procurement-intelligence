"""Temporary links to a plan or an assessment: a snapshot of what the page showed, kept for a few days.

The page sends the same body it sends for a Word file; the link opens a read-only page (web /shared?id=...) with the
plan or assessment and its export buttons. Links need a signed-in planner like the rest of the app; they expire after
PROCINTEL_SHARE_DAYS days (default 7); the creator can edit the snapshot behind a link (update) or delete it sooner. A snapshot does not change when the plan
does: it is what was shared, and says when.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from procintel.pipeline import store as pipeline_store

KINDS = ("plan", "assessment")
MAX_BYTES = 2 * 2**20


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def days() -> int:
    return max(1, min(90, int(os.environ.get("PROCINTEL_SHARE_DAYS", "7"))))


def connect(db_path: Path | None = None):
    con = pipeline_store.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS share (share_id VARCHAR, kind VARCHAR, body VARCHAR, created_by VARCHAR,
                   created_at TIMESTAMP, expires_at TIMESTAMP)""")
    return con


def create(kind: str, body: dict, created_by: str | None, db_path: Path | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    text = json.dumps(body)
    if len(text) > MAX_BYTES:
        raise ValueError("too large to share")
    sid, now = secrets.token_urlsafe(12), _now()
    con = connect(db_path)
    try:
        con.execute("DELETE FROM share WHERE expires_at < ?", [now])
        con.execute("INSERT INTO share VALUES (?, ?, ?, ?, ?, ?)", [sid, kind, text, created_by, now, now + timedelta(days=days())])
    finally:
        con.close()
    return {"id": sid, "kind": kind, "createdAt": now.isoformat() + "Z", "expiresAt": (now + timedelta(days=days())).isoformat() + "Z"}


def get(sid: str, db_path: Path | None = None) -> dict | None:
    """The share, or None when there is none or it has expired."""
    con = connect(db_path)
    try:
        r = con.execute("SELECT kind, body, created_by, created_at, expires_at FROM share WHERE share_id = ? AND expires_at >= ?",
                        [sid, _now()]).fetchone()
    finally:
        con.close()
    if not r:
        return None
    return {"id": sid, "kind": r[0], "body": json.loads(r[1]), "createdBy": r[2], "createdAt": r[3].isoformat() + "Z",
            "expiresAt": r[4].isoformat() + "Z"}


def update(sid: str, body: dict, by: str | None, db_path: Path | None = None) -> dict | None:
    """Replace the snapshot of a link its creator edited (the link stays the same, its expiry starts again); None when the
    link is gone or not the caller's."""
    text = json.dumps(body)
    if len(text) > MAX_BYTES:
        raise ValueError("too large to share")
    now = _now()
    con = connect(db_path)
    try:
        r = con.execute("SELECT created_by FROM share WHERE share_id = ? AND expires_at >= ?", [sid, now]).fetchone()
        if not r or not by or r[0] != by:
            return None
        con.execute("UPDATE share SET body = ?, created_at = ?, expires_at = ? WHERE share_id = ?",
                    [text, now, now + timedelta(days=days()), sid])
    finally:
        con.close()
    return get(sid, db_path)


def delete(sid: str, by: str | None, admin: bool = False, db_path: Path | None = None) -> bool:
    con = connect(db_path)
    try:
        r = con.execute("SELECT created_by FROM share WHERE share_id = ?", [sid]).fetchone()
        if not r or not (admin or (by and r[0] == by)):
            return False
        con.execute("DELETE FROM share WHERE share_id = ?", [sid])
        return True
    finally:
        con.close()
