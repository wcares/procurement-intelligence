"""Prompts (procintel.core.prompts): their versions, saving a candidate, activating a version."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from procintel.api import access
from procintel.api.schemas import PromptActivate, PromptSave
from procintel.core import prompts
from procintel.jobs import store as jobs_store

router = APIRouter()


@router.get("/prompts")
def get_prompts() -> dict:
    return {"prompts": prompts.listing()}


@router.post("/prompts/{name}")
def post_prompt(name: str, req: PromptSave, request: Request) -> dict:
    """Save a new version as a candidate; prompts used in answering get an evaluation job against the active one."""
    if not access.is_admin_client(request):
        return access.refuse("changing a prompt")
    if name not in prompts.PROMPTS:
        return JSONResponse({"error": f"no prompt named {name!r}"}, status_code=404)
    try:
        v = prompts.save(name, req.text, req.note)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    job = None
    if prompts.PROMPTS[name].evaluated_by == "answers":
        job = jobs_store.enqueue("prompt_evaluate", f"prompt {name} version {v}", {"name": name, "version": v},
                                 dedupe=False)
    return {"version": v, "evaluationJob": job}


@router.post("/prompts/{name}/activate")
def activate_prompt(name: str, req: PromptActivate, request: Request) -> dict:
    if not access.is_admin_client(request):
        return access.refuse("activating a prompt")
    try:
        prompts.activate(name, req.version)
    except (KeyError, FileNotFoundError):
        return JSONResponse({"error": f"no version {req.version} of prompt {name!r}"}, status_code=404)
    return {"prompts": prompts.listing()}
