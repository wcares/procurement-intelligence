"""Background jobs and data reload."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from procintel.api import access, background, security
from datetime import datetime, timedelta, timezone

from procintel.api.schemas import JobLater, JobRequest
from procintel.api.state import reload_lock, reload_state, state
from procintel.jobs import store as jobs_store

router = APIRouter()
admin = [Depends(security.require("admin"))]


@router.post("/admin/reload")
def post_reload(request: Request) -> dict:
    """Load refreshed data without restarting (procintel.ingestion.refresh calls this when given --reload-url): from an
    admin's session or from an administrative client address (the refresh script); about a minute of work."""
    if not access.is_admin(request):
        return access.refuse("reload")
    if reload_lock.locked():
        return JSONResponse({"error": "a reload is already running"}, status_code=409)
    secs = reload_state()
    return {"ok": True, "seconds": round(secs, 1), "passages": len(state().retriever.records)}


@router.get("/jobs", dependencies=admin)
def get_jobs() -> dict:
    names = {v: k for k, v in jobs_store.PRIORITIES.items()}
    jobs = [j | {"priority": names.get(j.get("priority"), "normal")} for j in jobs_store.recent()]
    kinds = {k: jobs_store.DEFAULT_PRIORITY.get(k, "normal") for k in sorted(jobs_store.DEFAULT_PRIORITY)}
    from procintel.jobs import worker
    return {"jobs": jobs, "kinds": kinds, "lightKinds": sorted(worker.LIGHT)} | background.status()


@router.post("/jobs", dependencies=admin)
def post_job(req: JobRequest, request: Request) -> dict:
    if not access.is_admin(request):
        return access.refuse("queueing a job")
    jid = jobs_store.enqueue(req.kind, req.reason, priority=req.priority)
    return {"queued": jid, "note": None if jid else "a job of this kind is already waiting or running"}


LATER = {"30m": timedelta(minutes=30), "1h": timedelta(hours=1), "2h": timedelta(hours=2), "4h": timedelta(hours=4)}
TONIGHT_HOUR = 22   # "tonight": from this hour, local time, when nobody is expected to use the app


def start_time(when: str, now: datetime | None = None) -> datetime:
    """The naive UTC time a job may start for a choice in the queue (the store keeps UTC)."""
    now = now or datetime.now().astimezone()                      # local time with its offset
    if when == "tonight":
        at = now.replace(hour=TONIGHT_HOUR, minute=0, second=0, microsecond=0)
        at = max(at, now)
    else:
        at = now + LATER[when]
    return at.astimezone(timezone.utc).replace(tzinfo=None)


def _queue_action(ok: bool) -> dict:
    if not ok:
        return JSONResponse({"error": "only a waiting or running job can be paused or moved"}, status_code=409)
    return get_jobs()


@router.post("/jobs/{jid}/pause", dependencies=admin)
def post_pause(jid: str) -> dict:
    """Pause a job until it is resumed; a running one stops after its current step and keeps its place."""
    return _queue_action(jobs_store.hold(jid))


@router.post("/jobs/{jid}/resume", dependencies=admin)
def post_resume(jid: str) -> dict:
    """Undo a pause or a later start: the job runs as soon as the worker can take it."""
    return _queue_action(jobs_store.resume(jid))


@router.post("/jobs/{jid}/later", dependencies=admin)
def post_later(jid: str, req: JobLater) -> dict:
    """Start a job no earlier than the chosen time; a running one stops after its current step and resumes then."""
    return _queue_action(jobs_store.later(jid, start_time(req.when)))
