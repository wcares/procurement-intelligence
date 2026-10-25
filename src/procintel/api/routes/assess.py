"""Planned-package assessment and the form options."""
from __future__ import annotations

from fastapi import APIRouter

from procintel.api.state import state
from procintel.learning import feedback
from procintel.prediction.assess import assess as run_assess

from procintel.api.schemas import AssessRequest, AssessResponse, Options

router = APIRouter()


@router.get("/options", response_model=Options)
def get_options() -> dict:
    return state().options


@router.post("/assess", response_model=AssessResponse)
def post_assess(req: AssessRequest) -> dict:
    s = state()
    body = req.model_dump()
    out = run_assess(s.retriever, s.bench, s.governance, body, s.timeline_model, s.region.get(body["countryCode"]),
                     s.country_name.get(body["countryCode"], ""), s.rebid, s.rebid_cost, s.amendments, s.wgi)
    s.flag_evidence.attach(out["risks"], body, s.bench, out["timeline"], out["governance"], out["wgi"])
    try:
        out["similarPackages"] = s.similar.search(body.get("description") or "", body["procGroup"])
    except Exception:  # embedding server down: the assessment stands without this section
        out["similarPackages"] = []
    feedback.log_response("assess", body, out)
    return out
