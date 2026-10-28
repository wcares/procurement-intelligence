"""Cited answers to free-text questions."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from procintel.answering.answer import ask as run_ask, ask_events
from procintel.api import security
from procintel.api.schemas import AskRequest, AskResponse
from procintel.api.state import state
from procintel.auth import service
from procintel.learning import feedback

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def post_ask(req: AskRequest, request: Request) -> dict:
    started = time.monotonic()
    out = run_ask(state().retriever, req.question, req.countryCode, req.procGroup)
    feedback.log_response("ask", req.model_dump(), out, user_id=service.pseudonym(security.user_of(request)),
                          duration_ms=round((time.monotonic() - started) * 1000))
    return out


@router.post("/ask/stream")
def post_ask_stream(req: AskRequest, request: Request) -> StreamingResponse:
    """/ask as server-sent events: the stages, the evidence found and each checked sentence as they exist, then the
    same answer /ask returns (procintel.answering.answer.ask_events). A failure ends the stream with an error event."""
    user = service.pseudonym(security.user_of(request))
    started = time.monotonic()

    def events():
        try:
            for ev in ask_events(state().retriever, req.question, req.countryCode, req.procGroup):
                if ev["type"] == "done":
                    feedback.log_response("ask", req.model_dump(), ev["result"], user_id=user,
                                          duration_ms=round((time.monotonic() - started) * 1000))
                    ev = {**ev, "result": AskResponse(**ev["result"]).model_dump()}
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as e:  # the page shows the message and can retry
            yield f"data: {json.dumps({'type': 'error', 'message': f'{type(e).__name__}: {e}'[:300]})}\n\n"

    # no-transform and X-Accel-Buffering: proxies (Cloudflare, nginx) must pass each event on at once, not collect them
    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
