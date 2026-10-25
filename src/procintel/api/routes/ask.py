"""Cited answers to free-text questions."""
from __future__ import annotations

from fastapi import APIRouter

from procintel.answering.answer import ask as run_ask
from procintel.api.state import state
from procintel.learning import feedback

from procintel.api.schemas import AskRequest, AskResponse

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def post_ask(req: AskRequest) -> dict:
    out = run_ask(state().retriever, req.question, req.countryCode, req.procGroup)
    feedback.log_response("ask", req.model_dump(), out)
    return out
