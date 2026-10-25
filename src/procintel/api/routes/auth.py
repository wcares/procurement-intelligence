"""Sign-in, the current user, and account management (admins)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from procintel.api import security
from procintel.api.schemas import Login, NewUser, UserUpdate
from procintel.auth import service, store

router = APIRouter()
admin = [Depends(security.require("admin"))]


@router.post("/auth/login")
def login(req: Login, request: Request, response: Response) -> dict:
    if service.mode() == "off":
        return {"username": "local", "role": "admin", "mode": "off"}
    try:
        token, user = service.login(req.username, req.password, request.client.host if request.client else "?")
    except service.LoginRefused as e:
        return JSONResponse({"error": str(e)}, status_code=e.status)
    security.set_session(response, token)
    return user | {"mode": "local"}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    if t := security.token(request):
        service.logout(t)
    security.clear_session(response)
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request) -> dict:
    user = security.current_user(request)
    if user is None:
        return JSONResponse({"error": "not signed in", "mode": service.mode()}, status_code=401)
    return user | {"mode": service.mode()}


@router.get("/auth/users", dependencies=admin)
def list_users() -> dict:
    return {"users": store.users()}


@router.post("/auth/users", dependencies=admin)
def create_user(req: NewUser) -> dict:
    try:
        service.create_user(req.username, req.password, req.role)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"users": store.users()}


@router.patch("/auth/users/{username}", dependencies=admin)
def update_user(username: str, req: UserUpdate, request: Request) -> dict:
    if username == security.user_of(request) and (req.active is False or req.role == "planner"):
        return JSONResponse({"error": "you cannot remove your own admin access"}, status_code=400)
    try:
        service.update_user(username, req.role, req.active, req.password)
    except KeyError:
        return JSONResponse({"error": f"no user {username!r}"}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"users": store.users()}
