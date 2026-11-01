"""Temporary read-only links to a plan or an assessment (procintel.reports.shares)."""
from __future__ import annotations

import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from procintel.auth import has_role
from procintel.reports import shares

router = APIRouter()
_ID = re.compile(r"^[A-Za-z0-9_-]{8,40}$")


def _user(request: Request) -> tuple[str | None, bool]:
    user = getattr(request.state, "user", None)
    return (user["username"] if user else None), bool(user and has_role(user["role"], "admin"))


@router.post("/shares")
async def post_share(request: Request) -> dict:
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("body"), dict):
        return JSONResponse({"error": "send {kind, body}"}, status_code=400)
    try:
        return shares.create(str(body.get("kind")), body["body"], _user(request)[0])
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get("/shares/{sid}")
def get_share(sid: str) -> dict:
    found = shares.get(sid) if _ID.match(sid) else None
    return found if found else JSONResponse({"error": "this link has expired or does not exist"}, status_code=404)


@router.put("/shares/{sid}")
async def put_share(sid: str, request: Request) -> dict:
    """The creator saves an edited plan or assessment behind the same link; anyone else gets 404 (and can make a new link)."""
    body = await request.json()
    if not _ID.match(sid) or not isinstance(body, dict) or not isinstance(body.get("body"), dict):
        return JSONResponse({"error": "send {body}"}, status_code=400)
    try:
        out = shares.update(sid, body["body"], _user(request)[0])
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return out if out else JSONResponse({"error": "no such link of yours"}, status_code=404)


@router.delete("/shares/{sid}")
def delete_share(sid: str, request: Request) -> dict:
    who, admin = _user(request)
    if not (_ID.match(sid) and shares.delete(sid, who, admin)):
        return JSONResponse({"error": "no such link of yours"}, status_code=404)
    return {"deleted": sid}
