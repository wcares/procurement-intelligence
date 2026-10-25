"""User feedback on responses and what the feedback review asks a person to check."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from procintel.jobs import store as jobs_store
from procintel.learning import feedback, feedback_review

from procintel.api.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
def post_feedback(req: FeedbackRequest) -> dict:
    try:
        fid = feedback.add(req.responseId, req.rating, req.citationId, req.comment)
        jobs_store.enqueue("feedback_review", "new feedback")  # runs when the app is idle
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "feedbackId": fid}


@router.get("/feedback/review")
def get_feedback_review() -> dict:
    """What feedback asks a person to look at, as of the last feedback_review job."""
    return {"items": feedback_review.items(), "demoted": sorted(feedback_review.load_demoted()),
            "demoteAfter": feedback_review.DEMOTE_MIN}
