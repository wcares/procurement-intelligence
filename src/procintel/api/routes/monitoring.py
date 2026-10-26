"""Monitoring of ongoing work (procintel.monitoring): projects and packages with their status and live forecasts for
planners; the status parameters with their dry run for admins (per route)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from procintel.api import access, security
from procintel.insights import alerts
from procintel.monitoring import status, status_rules, views

router = APIRouter()
admin = [Depends(security.require("admin"))]


class Described(BaseModel):
    procGroup: str
    methodCode: str | None = None
    tenderStart: date | None = None
    awardDate: date | None = None
    contractDurationDays: int | None = None
    reissued: bool = False
    closingDate: date | None = None


@router.get("/monitoring/projects")
def get_projects(request: Request, scope: str = "ongoing") -> dict:
    """scope ongoing: every project with active packages; watched: the projects on the caller's watch-list."""
    only = None
    if scope == "watched":
        user = getattr(request.state, "user", None)
        only = alerts.get_watch(user["username"] if user else "local")["project"]
    return {"projects": views.projects(only), "scope": scope}


@router.get("/monitoring/projects/{project_id}")
def get_project(project_id: str) -> dict:
    p = views.project(project_id)
    return p if p else JSONResponse({"error": "no such project"}, status_code=404)


@router.get("/monitoring/package")
def get_package(id: str) -> dict:   # package ids contain slashes: a query parameter
    p = views.package(id)
    return p if p else JSONResponse({"error": "no such package"}, status_code=404)


@router.post("/monitoring/forecast")
def post_forecast(req: Described) -> dict:
    return views.describe({"proc_group": req.procGroup, "method_code": req.methodCode,
                           "tender_start": req.tenderStart.isoformat() if req.tenderStart else None,
                           "award_date": req.awardDate.isoformat() if req.awardDate else None,
                           "contract_duration_days": req.contractDurationDays, "reissued": req.reissued,
                           "closing_date": req.closingDate.isoformat() if req.closingDate else None})


@router.get("/monitoring/status-rules", dependencies=admin)
def get_rules() -> dict:
    return {"rules": status_rules.active(), "defaults": status_rules.DEFAULTS, "customised": status_rules.customised(),
            "counts": status.counts(status.classify(status.frame()))}


@router.post("/monitoring/status-rules/dry-run", dependencies=admin)
def post_dry_run(change: dict) -> dict:
    if errors := status_rules.validate(status_rules.active() | change):
        return JSONResponse({"error": "; ".join(errors)}, status_code=400)
    return status.dry_run(status.frame(), status_rules.active() | change)


@router.put("/monitoring/status-rules", dependencies=admin)
def put_rules(change: dict, request: Request) -> dict:
    if not access.is_admin_client(request):
        return access.refuse("changing the status rules")
    try:
        status_rules.save(status_rules.active() | change)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return get_rules()
