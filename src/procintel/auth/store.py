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
    con.execute("""CREATE TABLE IF NOT EXISTS sessions (token_hash VARCHAR PRIMARY KEY, username VARCHAR,
                   created_at TIMESTAMP, expires_at TIMESTAMP)""")
    con.execute("CREATE TABLE IF NOT EXISTS failed_logins (username VARCHAR, client VARCHAR, failed_at TIMESTAMP)")
    return con


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_user(username: str) -> dict | None:
    con = connect()
    try:
        r = con.execute("SELECT username, password_hash, role, active FROM users WHERE username = ?",
                        [username]).fetchone()
        return dict(zip(("username", "password_hash", "role", "active"), r)) if r else None
    finally:
        con.close()


def users() -> list[dict]:
    con = connect()
    try:
        q = con.execute("SELECT username, role, active, created_at, last_login FROM users ORDER BY username")
        return [{"username": u, "role": r, "active": a, "createdAt": c.isoformat() + "Z" if c else None,
                 "lastLogin": ll.isoformat() + "Z" if ll else None} for u, r, a, c, ll in q.fetchall()]
    finally:
        con.close()


def count_users() -> int:
    con = connect()
    try:
        return con.execute("SELECT count(*) FROM users").fetchone()[0]
    finally:
        con.close()


def add_user(username: str, password_hash: str, role: str) -> None:
    con = connect()
    try:
        con.execute("INSERT INTO users VALUES (?, ?, ?, true, ?, NULL)", [username, password_hash, role, _now()])
    finally:
        con.close()


def update_user(username: str, **fields) -> None:
    con = connect()
    try:
        for k, v in fields.items():
            con.execute(f"UPDATE users SET {k} = ? WHERE username = ?", [v, username])
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
