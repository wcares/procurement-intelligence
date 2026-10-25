"""Background jobs and data reload."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from procintel.api import access, background
from procintel.api.state import reload_lock, reload_state, state
from procintel.jobs import store as jobs_store

from procintel.api.schemas import JobRequest

router = APIRouter()


@router.post("/admin/reload")
def post_reload(request: Request) -> dict:
    """Load refreshed data without restarting (procintel.ingestion.refresh calls this when given --reload-url). Only
    from an administrative client: it rebuilds the search index and models, about a minute of work."""
    if not access.is_admin_client(request):
        return access.refuse("reload")
    if reload_lock.locked():
        return JSONResponse({"error": "a reload is already running"}, status_code=409)
    secs = reload_state()
    return {"ok": True, "seconds": round(secs, 1), "passages": len(state().retriever.records)}


@router.get("/jobs")
def get_jobs() -> dict:
    names = {v: k for k, v in jobs_store.PRIORITIES.items()}
    jobs = [j | {"priority": names.get(j.get("priority"), "normal")} for j in jobs_store.recent()]
    kinds = {k: jobs_store.DEFAULT_PRIORITY.get(k, "normal") for k in sorted(jobs_store.DEFAULT_PRIORITY)}
    return {"jobs": jobs, "kinds": kinds} | background.status()


@router.post("/jobs")
def post_job(req: JobRequest, request: Request) -> dict:
    if not access.is_admin_client(request):
        return access.refuse("queueing a job")
    jid = jobs_store.enqueue(req.kind, req.reason, priority=req.priority)
    return {"queued": jid, "note": None if jid else "a job of this kind is already waiting or running"}
