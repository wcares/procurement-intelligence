"""Word files of what the page shows (procintel.reports.word): the plan and a package assessment."""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from procintel.api.routes.intake import _who
from procintel.reports import word

router = APIRouter()
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_PACKAGES = 200


def _file(data: bytes, stem: str) -> Response:
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")[:60] or "export"
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{name}-{date.today()}.docx"'})


@router.post("/export/plan")
async def export_plan(request: Request) -> Response:
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("packages"), list) or len(body["packages"]) > MAX_PACKAGES:
        return JSONResponse({"error": "send the plan: packages, forecasts and the scheduled plan"}, status_code=400)
    return _file(word.plan_docx(body, _who(request)[0]), body.get("title") or "procurement-plan")


@router.post("/export/assessment")
async def export_assessment(request: Request) -> Response:
    body = await request.json()
    if not isinstance(body, dict) or not isinstance(body.get("response"), dict):
        return JSONResponse({"error": "send the assessment: request and response"}, status_code=400)
    req = body.get("request") or {}
    return _file(word.assessment_docx(body, _who(request)[0]),
                 f"assessment-{req.get('countryCode', '')}-{req.get('procGroup', '')}-{req.get('methodCode', '')}")
