"""Shadow builds (procintel.learning.shadows): their state and evaluation, and queueing build, evaluate, promote."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from procintel.api import access
from procintel.jobs import store as jobs_store
from procintel.learning import shadows

router = APIRouter()
JOB = {"build": "shadow_build", "evaluate": "shadow_evaluate", "promote": "shadow_promote"}


@router.get("/shadows")
def get_shadows() -> dict:
    return {"shadows": shadows.states(),
            "available": [{"name": s.name, "label": s.label} for s in shadows.SHADOWS.values()]}


@router.post("/shadows/{name}/{action}")
def post_shadow(name: str, action: Literal["build", "evaluate", "promote", "discard"], request: Request) -> dict:
    if not access.is_admin_client(request):
        return access.refuse(f"{action} of a shadow build")
    if name not in shadows.SHADOWS:
        return JSONResponse({"error": f"no shadow build named {name!r}"}, status_code=404)
    if action == "discard":
        shadows.discard(name)
        return {"discarded": name}
    jid = jobs_store.enqueue(JOB[action], f"{action} shadow {name} (requested)", {"name": name})
    return {"queued": jid, "note": None if jid else "a job of this kind is already waiting or running"}
