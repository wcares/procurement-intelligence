"""Cited answers to free-text questions."""
from __future__ import annotations

from fastapi import APIRouter, Request

from procintel.answering.answer import ask as run_ask
from procintel.api import security
from procintel.api.schemas import AskRequest, AskResponse
from procintel.api.state import state
from procintel.auth import service
from procintel.learning import feedback

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def post_ask(req: AskRequest, request: Request) -> dict:
    out = run_ask(state().retriever, req.question, req.countryCode, req.procGroup)
    feedback.log_response("ask", req.model_dump(), out, user_id=service.pseudonym(security.user_of(request)))
    return out
