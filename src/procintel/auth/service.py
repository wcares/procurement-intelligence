"""Logging in and out, the user behind a session, the first admin, and the pseudonymous id used in the logs."""
from __future__ import annotations

import hashlib
import os
import secrets
import threading
import time
from datetime import timedelta

from procintel.auth import ROLES, passwords, store
from procintel.core import paths

SESSION_LIFETIME = timedelta(hours=12)
MAX_FAILURES = 5                       # failed logins for a username or from a client ...
FAILURE_WINDOW = timedelta(minutes=15)  # ... within this window: further attempts are refused until it passes
_DUMMY = passwords.hash_password(secrets.token_hex(8))  # checked for unknown names, so timing reveals no usernames
# Each sign-in page admits only its roles, so an admin account is not used from the planner page or the other way round.
PORTALS = {"planner": ("planner", "reviewer"), "admin": ("admin",)}
REQUESTS_PER_CLIENT = 3                 # access requests (sign-up) from one client per hour ...
REQUESTS_PER_HOUR = 30                  # ... and from everyone, so the page cannot fill the accounts table
_requests: dict[str, list[float]] = {}
_requests_lock = threading.Lock()


class LoginRefused(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


def mode() -> str:
    m = os.environ.get("PROCINTEL_AUTH", "local").strip() or "local"
    if m not in ("local", "off"):
        raise ValueError(f"PROCINTEL_AUTH must be local or off, not {m!r}")
    return m


def login(username: str, password: str, client: str, portal: str | None = None) -> tuple[str, dict]:
    """(session token, user) or LoginRefused. portal: the sign-in page used ("planner" or "admin"), which admits only
    its roles; None (the API and older clients) admits every role. Only a correct password learns why an account was
    refused, so the messages reveal nothing to someone guessing."""
    if store.recent_failures(username, client, FAILURE_WINDOW) >= MAX_FAILURES:
        raise LoginRefused(f"too many failed attempts; try again in {FAILURE_WINDOW.seconds // 60} minutes", 429)
    user = store.get_user(username)
    ok = passwords.verify(password, user["password_hash"] if user else _DUMMY)
    if user and ok and not user["active"] and user["pending"]:
        raise LoginRefused("your access request is waiting for an administrator to approve it")
    if not (user and ok and user["active"]):
        store.record_failure(username, client)
        raise LoginRefused("wrong username or password")
    store.clear_failures(username)
    if portal is not None and user["role"] not in PORTALS[portal]:
        raise LoginRefused("this is an administrator account: use the administrator sign-in" if portal == "planner"
                           else "this is not an administrator account: use the planner sign-in")
    token = secrets.token_urlsafe(32)
    store.add_session(token, username, SESSION_LIFETIME)
    return token, {"username": username, "role": user["role"]}


def logout(token: str) -> None:
    store.end_session(token)


def user_for(token: str | None) -> dict | None:
    if mode() == "off":
        return {"username": "local", "role": "admin"}
    return store.session_user(token) if token else None


def create_user(username: str, password: str, role: str, requested: bool = False) -> None:
    username = username.strip()
    if not username or len(username) > 60:
        raise ValueError("a username of 1 to 60 characters")
    if role not in ROLES:
        raise ValueError(f"role must be one of {', '.join(ROLES)}")
    if problem := passwords.check_strength(password):
        raise ValueError(f"password: {problem}")
    if store.get_user(username):
        raise ValueError("this username exists")
    store.add_user(username, passwords.hash_password(password), role, requested)


def request_access(username: str, password: str, client: str) -> None:
    """Sign-up: a planner account that stays inactive until an admin enables it (Settings, Accounts). Nobody can ask for
    a higher role here; an admin changes the role when approving. ValueError for a bad name or password, LoginRefused
    when too many requests came in."""
    now = time.monotonic()
    with _requests_lock:
        mine = [t for t in _requests.get(client, []) if now - t < 3600]
        if len(mine) >= REQUESTS_PER_CLIENT or store.recent_requests(timedelta(hours=1)) >= REQUESTS_PER_HOUR:
            raise LoginRefused("too many access requests; try again in an hour", 429)
        create_user(username, password, "planner", requested=True)
        _requests[client] = mine + [now]


def update_user(username: str, role: str | None = None, active: bool | None = None, password: str | None = None) -> None:
    if not store.get_user(username):
        raise KeyError(username)
    fields: dict = {}
    if role is not None:
        if role not in ROLES:
            raise ValueError(f"role must be one of {', '.join(ROLES)}")
        fields["role"] = role
    if active is not None:
        fields["active"] = active
    if password is not None:
        if problem := passwords.check_strength(password):
            raise ValueError(f"password: {problem}")
        fields["password_hash"] = passwords.hash_password(password)
    if fields:
        store.update_user(username, **fields)


def ensure_first_admin() -> str | None:
    """With no accounts yet, create the admin named by PROCINTEL_ADMIN_USER / PROCINTEL_ADMIN_PASSWORD."""
    if mode() != "local" or store.count_users():
        return None
    user, pw = os.environ.get("PROCINTEL_ADMIN_USER", "").strip(), os.environ.get("PROCINTEL_ADMIN_PASSWORD", "")
    if not user or not pw:
        return None
    create_user(user, pw, "admin")
    return user


def pseudonym(username: str | None) -> str | None:
    """A stable id for the logs that does not show the username (salted hash; the salt stays in the data folder)."""
    if not username:
        return None
    f = paths.DATA_DIR / "auth_salt"
    salt = os.environ.get("PROCINTEL_USER_ID_SALT") or (f.read_text().strip() if f.exists() else None)
    if not salt:
        salt = secrets.token_hex(16)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(salt)
        f.chmod(0o600)
    return hashlib.sha256(f"{salt}:{username}".encode()).hexdigest()[:16]
