"""Planned-package assessment and the form options."""
from __future__ import annotations

import time

from fastapi import APIRouter, Request

from procintel.api import security
from procintel.api.schemas import AssessRequest, AssessResponse, Options
from procintel.api.state import state
from procintel.auth import service
from procintel.learning import feedback
from procintel.prediction import stages
from procintel.prediction.assess import assess as run_assess

router = APIRouter()


@router.get("/options", response_model=Options)
def get_options() -> dict:
    return state().options


@router.post("/assess", response_model=AssessResponse)
def post_assess(req: AssessRequest, request: Request) -> dict:
    started = time.monotonic()
    s = state()
    body = req.model_dump()
    out = run_assess(s.retriever, s.bench, s.governance, body, s.timeline_model, s.region.get(body["countryCode"]),
                     s.country_name.get(body["countryCode"], ""), s.rebid, s.rebid_cost, s.amendments, s.wgi)
    s.flag_evidence.attach(out["risks"], body, s.bench, out["timeline"], out["governance"], out["wgi"])
    out["stages"] = stages.for_package(s.stage_stats, body["procGroup"], body["methodCode"])
    stages.place_risks(out["risks"])
    try:
        out["similarPackages"] = s.similar.search(body.get("description") or "", body["procGroup"])
    except Exception:  # embedding server down: the assessment stands without this section
        out["similarPackages"] = []
    feedback.log_response("assess", body, out, user_id=service.pseudonym(security.user_of(request)),
                          duration_ms=round((time.monotonic() - started) * 1000))
    return out
