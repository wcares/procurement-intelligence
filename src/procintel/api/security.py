"""Who is calling: the session cookie names a signed-in user (procintel.auth); require() guards an endpoint by role.

The user is put on request.state.user for the route (the response log records a pseudonymous id of it).
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request, Response

from procintel.auth import service

COOKIE = "procintel_session"


def token(request: Request) -> str | None:
    return request.cookies.get(COOKIE)


def current_user(request: Request) -> dict | None:
    return service.user_for(token(request))


def require(role: str):
    """A FastAPI dependency: 401 without a session, 403 when an admin endpoint is called by a planner."""
    def dependency(request: Request) -> dict:
        user = current_user(request)
        if user is None:
            raise HTTPException(401, "sign in first")
        if role == "admin" and user["role"] != "admin":
            raise HTTPException(403, "this needs the admin role")
        request.state.user = user
        return user
    dependency.__name__ = f"require_{role}"
    return dependency


def set_session(response: Response, value: str) -> None:
    response.set_cookie(COOKIE, value, max_age=int(service.SESSION_LIFETIME.total_seconds()), httponly=True,
                        samesite="lax", secure=os.environ.get("PROCINTEL_COOKIE_SECURE", "1") != "0", path="/")


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


def user_of(request: Request) -> str | None:
    """The signed-in username for this request (set by require), or None."""
    user = getattr(request.state, "user", None)
    return user["username"] if user else None
