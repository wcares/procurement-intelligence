"""User feedback on responses and what the feedback review asks a person to check."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from procintel.api import security
from procintel.api.schemas import FeedbackRequest, FeedbackResponse
from procintel.auth import service
from procintel.jobs import store as jobs_store
from procintel.learning import feedback, feedback_review

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
def post_feedback(req: FeedbackRequest, request: Request) -> dict:
    try:
        fid = feedback.add(req.responseId, req.rating, req.citationId, req.comment,
                           user_id=service.pseudonym(security.user_of(request)))
        jobs_store.enqueue("feedback_review", "new feedback")  # runs when the app is idle
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "feedbackId": fid}


@router.get("/feedback/review", dependencies=[Depends(security.require("admin"))])
def get_feedback_review() -> dict:
    """What feedback asks a person to look at, as of the last feedback_review job."""
    return {"items": feedback_review.items(), "demoted": sorted(feedback_review.load_demoted()),
            "demoteAfter": feedback_review.DEMOTE_MIN}
