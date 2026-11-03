"""Accounts, sessions and failed logins. A session token is stored only as its hash, so a copy of this database
does not let anyone sign in."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

from procintel.core import db, paths


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = db_path or paths.AUTH_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS users (username VARCHAR PRIMARY KEY, password_hash VARCHAR,
                   role VARCHAR, active BOOLEAN, created_at TIMESTAMP, last_login TIMESTAMP)""")
    # set while an account asked for on the sign-up page waits for an admin's approval (older stores lack it)
    con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS requested_at TIMESTAMP")
    con.execute("""CREATE TABLE IF NOT EXISTS sessions (token_hash VARCHAR PRIMARY KEY, username VARCHAR,
                   created_at TIMESTAMP, expires_at TIMESTAMP)""")
    con.execute("CREATE TABLE IF NOT EXISTS failed_logins (username VARCHAR, client VARCHAR, failed_at TIMESTAMP)")
    return con


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_user(username: str) -> dict | None:
    con = connect()
    try:
        r = con.execute("SELECT username, password_hash, role, active, requested_at IS NOT NULL FROM users WHERE username = ?",
                        [username]).fetchone()
        return dict(zip(("username", "password_hash", "role", "active", "pending"), r)) if r else None
    finally:
        con.close()


def users() -> list[dict]:
    con = connect()
    try:
        q = con.execute("SELECT username, role, active, created_at, last_login, requested_at FROM users ORDER BY username")
        return [{"username": u, "role": r, "active": a, "createdAt": c.isoformat() + "Z" if c else None,
                 "lastLogin": ll.isoformat() + "Z" if ll else None, "requestedAt": rq.isoformat() + "Z" if rq else None}
                for u, r, a, c, ll, rq in q.fetchall()]
    finally:
        con.close()


def count_users() -> int:
    con = connect()
    try:
        return con.execute("SELECT count(*) FROM users").fetchone()[0]
    finally:
        con.close()


def add_user(username: str, password_hash: str, role: str, requested: bool = False) -> None:
    """A working account, or with requested an inactive one waiting for an admin's approval."""
    con = connect()
    try:
        con.execute("""INSERT INTO users (username, password_hash, role, active, created_at, last_login, requested_at)
                       VALUES (?, ?, ?, ?, ?, NULL, ?)""", [username, password_hash, role, not requested, _now(), _now() if requested else None])
    finally:
        con.close()


def drop_retired_roles() -> int:
    """At startup: the reviewer role was dropped (2026-11-03); such an account keeps the planner app, the lower of the
    two roles. Returns how many accounts changed."""
    con = connect()
    try:
        n = con.execute("SELECT count(*) FROM users WHERE role = 'reviewer'").fetchone()[0]
        if n:
            con.execute("UPDATE users SET role = 'planner' WHERE role = 'reviewer'")
        return n
    finally:
        con.close()


def recent_requests(since: timedelta) -> int:
    con = connect()
    try:
        return con.execute("SELECT count(*) FROM users WHERE requested_at > ?", [_now() - since]).fetchone()[0]
    finally:
        con.close()


def delete_request(username: str) -> bool:
    """Remove an access request that was never approved (an account in use is disabled instead, keeping its history)."""
    con = connect()
    try:
        if not con.execute("SELECT count(*) FROM users WHERE username = ? AND requested_at IS NOT NULL", [username]).fetchone()[0]:
            return False
        con.execute("DELETE FROM users WHERE username = ?", [username])
        return True
    finally:
        con.close()


def update_user(username: str, **fields) -> None:
    con = connect()
    try:
        for k, v in fields.items():
            con.execute(f"UPDATE users SET {k} = ? WHERE username = ?", [v, username])
        if fields.get("active") is True:   # enabling a requested account approves the request
            con.execute("UPDATE users SET requested_at = NULL WHERE username = ?", [username])
        if fields.get("active") is False or "password_hash" in fields or "role" in fields:
            con.execute("DELETE FROM sessions WHERE username = ?", [username])  # changes take effect at once
    finally:
        con.close()


def add_session(token: str, username: str, lifetime: timedelta) -> None:
    con = connect()
    try:
        con.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", [token_hash(token), username, _now(), _now() + lifetime])
        con.execute("UPDATE users SET last_login = ? WHERE username = ?", [_now(), username])
        con.execute("DELETE FROM sessions WHERE expires_at < ?", [_now()])
    finally:
        con.close()


def session_user(token: str) -> dict | None:
    con = connect()
    try:
        r = con.execute("""SELECT u.username, u.role FROM sessions s JOIN users u USING (username)
                           WHERE s.token_hash = ? AND s.expires_at > ? AND u.active""",
                        [token_hash(token), _now()]).fetchone()
        return {"username": r[0], "role": r[1]} if r else None
    finally:
        con.close()


def end_session(token: str) -> None:
    con = connect()
    try:
        con.execute("DELETE FROM sessions WHERE token_hash = ?", [token_hash(token)])
    finally:
        con.close()


def record_failure(username: str, client: str) -> None:
    con = connect()
    try:
        con.execute("INSERT INTO failed_logins VALUES (?, ?, ?)", [username, client, _now()])
        con.execute("DELETE FROM failed_logins WHERE failed_at < ?", [_now() - timedelta(days=1)])
    finally:
        con.close()


def recent_failures(username: str, client: str, window: timedelta) -> int:
    con = connect()
    try:
        return con.execute("SELECT count(*) FROM failed_logins WHERE (username = ? OR client = ?) AND failed_at > ?",
                           [username, client, _now() - window]).fetchone()[0]
    finally:
        con.close()


def clear_failures(username: str) -> None:
    con = connect()
    try:
        con.execute("DELETE FROM failed_logins WHERE username = ?", [username])
    finally:
        con.close()
