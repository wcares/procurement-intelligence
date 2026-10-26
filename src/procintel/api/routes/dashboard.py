"""The home dashboard: headline numbers, worst-to-best rankings, trends, heat map, problem mix and the records behind
every number (procintel.insights.dashboard); what changed recently (procintel.insights.recent)."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from procintel.api.state import state
from procintel.insights import dashboard, recent

router = APIRouter()


def _refuse(e: Exception) -> JSONResponse:
    return JSONResponse({"error": str(e).strip("'")}, status_code=400)


@router.get("/dashboard")
def get_dashboard() -> dict:
    d = state().dashboard
    return {"summary": d.summary(), "measures": dashboard.measures(), "groups": dashboard.GROUPS,
            "trends": d.trends(), "problemMix": d.problem_mix(), "fewProjects": dashboard.FEW_PROJECTS}


@router.get("/dashboard/ranking")
def get_ranking(measure: str = "delay", group: str = "country") -> dict:
    try:
        return state().dashboard.ranking(measure, group)
    except (KeyError, ValueError) as e:
        return _refuse(e)


@router.get("/dashboard/heatmap")
def get_heatmap(measure: str = "delay", min_n: int = 5) -> dict:
    try:
        return state().dashboard.heatmap(measure, min_n)
    except (KeyError, ValueError) as e:
        return _refuse(e)


@router.get("/dashboard/records")
def get_records(group: str, key: str, measure: str = "delay", method: str | None = None) -> dict:
    try:
        return state().dashboard.records(group, key, measure, method)
    except (KeyError, ValueError) as e:
        return _refuse(e)


@router.get("/dashboard/recent")
def get_recent(days: int = recent.DAYS) -> dict:
    return recent.recent(max(1, min(days, 90)))
