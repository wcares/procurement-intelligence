"""Insights for the signed-in planner (procintel.insights): their watch-list and the alerts it produced, and
recommendations for a planned package."""
from __future__ import annotations

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from procintel.api import security
from procintel.api.schemas import AssessRequest
from procintel.api.state import state
from procintel.auth import service
from procintel.insights import alerts, history, recommendations
from procintel.learning import feedback
from procintel.prediction.assess import assess as run_assess

router = APIRouter()
LOCAL = "local"   # the user when sign-in is off (PROCINTEL_AUTH=off): one shared watch-list


class Watch(BaseModel):
    watch: dict[str, list[str]]


class Read(BaseModel):
    ids: list[str] | None = None   # None: all


def _user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user["username"] if user else LOCAL


@router.get("/insights/watch")
def get_watch(request: Request) -> dict:
    return {"watch": alerts.get_watch(_user(request)), "kinds": list(alerts.KINDS)}


@router.put("/insights/watch")
def put_watch(req: Watch, request: Request) -> dict:
    try:
        return {"watch": alerts.set_watch(_user(request), req.watch), "kinds": list(alerts.KINDS)}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.get("/insights/alerts")
def get_alerts(request: Request, limit: int = 50) -> dict:
    return alerts.recent(_user(request), max(1, min(limit, 200)))


@router.post("/insights/alerts/read")
def post_read(req: Read, request: Request) -> dict:
    alerts.mark_read(_user(request), req.ids)
    return alerts.recent(_user(request))


@router.post("/insights/recommendations")
def post_recommendations(req: AssessRequest, request: Request) -> dict:
    """For the package on the Assess form: method alternatives from the statistics and, for its flagged risks, what
    past projects did (cited). Takes up to a minute (one answer per risk); logged so accept / dismiss feed back."""
    started = time.monotonic()
    s = state()
    body = req.model_dump()
    assessed = run_assess(s.retriever, s.bench, s.governance, body, s.timeline_model, s.region.get(body["countryCode"]),
                          s.country_name.get(body["countryCode"], ""), s.rebid, s.rebid_cost, s.amendments, s.wgi)
    labels = {m["code"]: m["label"] for m in s.options["methods"]}
    out = recommendations.for_package(s.retriever, s.bench, body, assessed["risks"], labels)
    feedback.log_response("recommend", body, out, user_id=service.pseudonym(security.user_of(request)),
                          duration_ms=round((time.monotonic() - started) * 1000))
    return out


@router.get("/insights/recommendations/history")
def get_history(request: Request, limit: int = 50) -> dict:
    """The planner's past recommendations with what they decided, and accept / dismiss counts over everyone's."""
    return history.past(service.pseudonym(security.user_of(request)), max(1, min(limit, 200)))


@router.get("/insights/trend")
def get_trend(procGroup: str, methodCode: str | None = None, countryCode: str | None = None) -> dict:
    """Award time by tender year for the package on the form (procintel.insights.dashboard.award_trend)."""
    return state().dashboard.award_trend(procGroup, methodCode or None, countryCode or None)
