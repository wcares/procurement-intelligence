"""Runtime settings (procintel.api.config): values, saved profiles, and the search-quality comparison."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from procintel.api import config
from procintel.api.state import state
from procintel.learning import evaluate

from procintel.api.schemas import CompareRequest, ConfigResponse, ConfigUpdate, ProfileApply, ProfileSave

router = APIRouter()


@router.get("/config", response_model=ConfigResponse)
def get_config() -> dict:
    return {"settings": config.listing()}


@router.put("/config", response_model=ConfigResponse)
def put_config(req: ConfigUpdate) -> dict:
    errors = config.update(req.values, save=req.save)
    if errors:
        return JSONResponse({"error": "invalid settings", "detail": errors}, status_code=400)
    return {"settings": config.listing()}


@router.get("/config/profiles")
def get_profiles() -> dict:
    return {"profiles": config.profiles()}


@router.post("/config/profiles")
def post_profile(req: ProfileSave) -> dict:
    try:
        config.save_profile(req.name)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"profiles": config.profiles()}


@router.post("/config/profiles/{name}/apply", response_model=ConfigResponse)
def apply_profile(name: str, req: ProfileApply) -> dict:
    errors = config.apply_profile(name, save=req.save)
    if errors:
        return JSONResponse({"error": "profile not applied", "detail": errors}, status_code=400)
    return {"settings": config.listing()}


@router.delete("/config/profiles/{name}")
def delete_profile(name: str) -> dict:
    if not config.delete_profile(name):
        return JSONResponse({"error": "no profile with this name"}, status_code=404)
    return {"profiles": config.profiles()}


@router.post("/config/compare")
def post_compare(req: CompareRequest) -> dict:
    """Search quality under the current settings and under the given values (not applied): keyword and hybrid
    precision@5 and recall@10 over the evaluation questions. Answers are not re-run (that takes about 90 minutes)."""
    out = config.compare(req.values, lambda: evaluate.retrieval_metrics(state().retriever))
    if "errors" in out:
        return JSONResponse({"error": "invalid settings", "detail": out["errors"]}, status_code=400)
    return out
