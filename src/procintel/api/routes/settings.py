"""Runtime settings (procintel.api.config): values, saved profiles, and the search-quality comparison."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import os
import time

from procintel.api import config, model_keys
from procintel.api.state import state
from procintel.core import llm
from procintel.learning import evaluate

from procintel.api.schemas import CompareRequest, ConfigResponse, ConfigUpdate, ModelKey, ModelTest, ProfileApply, ProfileSave

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


@router.get("/config/keys")
def get_keys() -> dict:
    """Per model: whether an API key is set and where from (this page or the environment). Never the key."""
    return {"keys": model_keys.status()}


@router.put("/config/keys/{role}")
def put_key(role: str, req: ModelKey) -> dict:
    """Set a model's API key (write-only); the next call to that model uses it."""
    try:
        model_keys.put(role, req.value)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"keys": model_keys.status()}


@router.delete("/config/keys/{role}")
def delete_key(role: str) -> dict:
    """Remove a key set on this page (a key from .env, if any, applies again)."""
    try:
        model_keys.remove(role)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"keys": model_keys.status()}


TEST_PROMPT = "In one short sentence, what is a procurement plan? Answer in English."
PREFIX = {"llm": llm.ANSWER, "judge": llm.JUDGE, "batch": llm.BATCH}


@router.post("/config/model-test")
def post_model_test(req: ModelTest) -> dict:
    """Send one short question to a model as it is set now (name, address, key) and report the reply and the time it
    took, so a switch can be checked at once. A key in an error message is replaced before the message is returned."""
    prefix = PREFIX[req.role]
    model = llm.model_name(prefix) or (llm.model_name() if req.role == "batch" else None)
    if not model:
        return {"ok": False, "model": None, "error": "no model is set for this role"}
    if req.role == "batch" and not llm.model_name(prefix):
        prefix = llm.ANSWER          # background work uses the answer model when it has none of its own
    started = time.monotonic()
    try:
        reply = llm.complete("You are a concise assistant.", TEST_PROMPT, prefix=prefix, max_tokens=300, timeout=90)
    except Exception as e:   # noqa: BLE001 - the error is the result
        msg = f"{type(e).__name__}: {e}"
        key = os.environ.get(f"{prefix}_API_KEY")
        if key:
            msg = msg.replace(key, "<key>")
        return {"ok": False, "model": model, "seconds": round(time.monotonic() - started, 1), "error": msg[:500]}
    return {"ok": True, "model": model, "address": os.environ.get(f"{prefix}_API_BASE") or "(the provider's own)",
            "seconds": round(time.monotonic() - started, 1), "reply": reply.strip()[:400]}
