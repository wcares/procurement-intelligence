"""Saved conversations: the planning chat and Ask, kept per user so a conversation can be reopened later.

Stored in the feedback database file (data/feedback.duckdb, one writer per file, each call opens and closes its own
connection): one row per conversation holding its messages as JSON, exactly what the page shows. A conversation belongs
to the pseudonymous id of the user who had it (procintel.auth.service.pseudonym) and is read back only for that id.
Removed after RETENTION_DAYS without an update (procintel.jobs.retention).

  conversation   id, user, kind (plan | ask), title (the first question), messages, created and updated times
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from procintel.core import db, paths

KINDS = ("plan", "ask")
MAX_BYTES = 1_500_000      # one conversation, as JSON
MAX_PER_USER = 100         # the newest this many are kept per user and kind
_LOCK = threading.Lock()


def _connect(db_path: Path | None):
    db_path = db_path or paths.FEEDBACK_DB   # resolved per call, so tests can point it at a temporary file
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS conversation (
        conversation_id VARCHAR PRIMARY KEY, user_id VARCHAR, kind VARCHAR, title VARCHAR, messages JSON,
        created_at TIMESTAMP, updated_at TIMESTAMP)""")
    return con


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _title(messages: list[dict]) -> str:
    """The first thing the user said: a plan chat message ("content") or an Ask question ("question")."""
    for m in messages:
        text = m.get("question") or (m.get("content") if m.get("role") == "user" else None)
        if isinstance(text, str) and text.strip():
            t = " ".join(text.split())
            return t if len(t) <= 70 else t[:67].rstrip() + "…"
    return "Conversation"


def save(user_id: str, conversation_id: str, kind: str, messages: list[dict], db_path: Path | None = None) -> dict:
    """Create or replace a conversation of this user. ValueError for a bad kind, an empty or oversized conversation, or an
    id that belongs to another user."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if not messages:
        raise ValueError("nothing to save")
    body = json.dumps(messages)
    if len(body) > MAX_BYTES:
        raise ValueError("this conversation is too long to save")
    title, now = _title(messages), _now()
    with _LOCK:
        con = _connect(db_path)
        try:
            row = con.execute("SELECT user_id FROM conversation WHERE conversation_id = ?", [conversation_id]).fetchone()
            if row and row[0] != user_id:
                raise ValueError("unknown conversation")
            if row:
                con.execute("UPDATE conversation SET messages = ?, title = ?, updated_at = ? WHERE conversation_id = ?",
                            [body, title, now, conversation_id])
            else:
                con.execute("INSERT INTO conversation VALUES (?, ?, ?, ?, ?, ?, ?)", [conversation_id, user_id, kind, title, body, now, now])
                con.execute("""DELETE FROM conversation WHERE user_id = ? AND kind = ? AND conversation_id NOT IN (
                    SELECT conversation_id FROM conversation WHERE user_id = ? AND kind = ? ORDER BY updated_at DESC LIMIT ?)""",
                            [user_id, kind, user_id, kind, MAX_PER_USER])
        finally:
            con.close()
    return {"id": conversation_id, "title": title, "updatedAt": now.isoformat() + "Z"}


def listing(user_id: str, kind: str, db_path: Path | None = None) -> list[dict]:
    """This user's conversations of a kind, newest first, without their messages."""
    with _LOCK:
        con = _connect(db_path)
        try:
            rows = con.execute("SELECT conversation_id, title, updated_at, json_array_length(messages) FROM conversation "
                               "WHERE user_id = ? AND kind = ? ORDER BY updated_at DESC", [user_id, kind]).fetchall()
        finally:
            con.close()
    return [{"id": r[0], "title": r[1], "updatedAt": r[2].isoformat() + "Z", "messages": r[3]} for r in rows]


def get(user_id: str, conversation_id: str, db_path: Path | None = None) -> dict | None:
    with _LOCK:
        con = _connect(db_path)
        try:
            r = con.execute("SELECT conversation_id, kind, title, messages, updated_at FROM conversation "
                            "WHERE conversation_id = ? AND user_id = ?", [conversation_id, user_id]).fetchone()
        finally:
            con.close()
    return {"id": r[0], "kind": r[1], "title": r[2], "messages": json.loads(r[3]), "updatedAt": r[4].isoformat() + "Z"} if r else None


def remove(user_id: str, conversation_id: str, db_path: Path | None = None) -> bool:
    with _LOCK:
        con = _connect(db_path)
        try:
            n = con.execute("SELECT count(*) FROM conversation WHERE conversation_id = ? AND user_id = ?",
                            [conversation_id, user_id]).fetchone()[0]
            con.execute("DELETE FROM conversation WHERE conversation_id = ? AND user_id = ?", [conversation_id, user_id])
        finally:
            con.close()
    return bool(n)
