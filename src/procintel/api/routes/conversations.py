"""Saved conversations (procintel.learning.conversations): list, open, save and delete the signed-in user's own."""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from procintel.api import security
from procintel.auth import service
from procintel.learning import conversations

router = APIRouter()
_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


class SaveConversation(BaseModel):
    kind: str
    messages: list[dict[str, Any]] = Field(max_length=400)


def _user(request: Request) -> str:
    return service.pseudonym(security.user_of(request)) or "local"


@router.get("/conversations")
def list_conversations(request: Request, kind: str = "plan") -> dict:
    if kind not in conversations.KINDS:
        return JSONResponse({"error": "unknown kind"}, status_code=400)
    return {"items": conversations.listing(_user(request), kind)}


@router.get("/conversations/{cid}")
def get_conversation(cid: str, request: Request):
    c = conversations.get(_user(request), cid) if _ID.match(cid) else None
    return c or JSONResponse({"error": "unknown conversation"}, status_code=404)


@router.put("/conversations/{cid}")
def put_conversation(cid: str, req: SaveConversation, request: Request):
    if not _ID.match(cid):
        return JSONResponse({"error": "bad id"}, status_code=400)
    try:
        return conversations.save(_user(request), cid, req.kind, req.messages)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str, request: Request):
    return {"ok": conversations.remove(_user(request), cid)} if _ID.match(cid) else JSONResponse({"error": "bad id"}, status_code=400)
