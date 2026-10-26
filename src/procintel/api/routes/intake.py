"""Uploads (procintel.intake): add a file, then follow it through extraction, classification and linking.

Planners upload and see their own files; a completion report a planner uploads waits for an admin to add it to the
evidence everyone searches (approve). Admins see every upload and remove any; a planner removes their own."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile
from fastapi.responses import JSONResponse

from procintel.api import security
from procintel.auth import has_role, service
from procintel.intake import extract, process, store

router = APIRouter()


def _who(request: Request) -> tuple[str | None, bool]:
    """(pseudonym of the caller, whether they are an admin)."""
    user = getattr(request.state, "user", None)
    return (service.pseudonym(user["username"]) if user else None), bool(user and has_role(user["role"], "admin"))


def _mine(up: dict | None, request: Request) -> dict | None:
    """The upload if the caller may see it (their own, or any for an admin), else None (reported as not found)."""
    who, admin = _who(request)
    return up if up and (admin or (who and up["uploaded_by"] == who)) else None


@router.post("/intake/uploads")
async def post_upload(file: UploadFile, request: Request, background: BackgroundTasks) -> dict:
    fmt = extract.format_of(file.filename or "")
    if fmt is None:
        return JSONResponse({"error": f"unsupported file type; accepted: {', '.join(sorted(extract.READERS))}"},
                            status_code=400)
    content = await file.read(extract.MAX_BYTES + 1)
    if len(content) > extract.MAX_BYTES:
        return JSONResponse({"error": f"the file is larger than {extract.MAX_BYTES // 2**20} MB"}, status_code=413)
    if not content:
        return JSONResponse({"error": "the file is empty"}, status_code=400)
    who, admin = _who(request)
    up = store.save(file.filename, content, fmt, who)
    if up["status"] == "received":   # seconds: extraction, classification, linking
        background.add_task(process.run, up["upload_id"], trusted=admin)
    return up


@router.get("/intake/uploads")
def get_uploads(request: Request, limit: int = 50) -> dict:
    who, admin = _who(request)
    rows = store.recent(max(1, min(limit, 200)), uploaded_by=None if admin else (who or "-"))
    return {"uploads": rows, "formats": sorted(extract.READERS), "maxMb": extract.MAX_BYTES // 2**20, "all": admin}


@router.delete("/intake/uploads/{upload_id}")
def delete_upload(upload_id: str, request: Request) -> dict:
    if not _mine(store.get(upload_id), request):
        return JSONResponse({"error": "no such upload"}, status_code=404)
    return process.remove(upload_id)


@router.post("/intake/uploads/{upload_id}/approve", dependencies=[Depends(security.require("admin"))])
def approve_upload(upload_id: str) -> dict:
    try:
        up = process.approve(upload_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return up if up else JSONResponse({"error": "no such upload"}, status_code=404)


@router.get("/intake/uploads/{upload_id}")
def get_upload(upload_id: str, request: Request) -> dict:
    up = _mine(store.get(upload_id), request)
    return up if up else JSONResponse({"error": "no such upload"}, status_code=404)
