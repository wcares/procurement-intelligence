"""Uploads (procintel.intake): add a file, then follow it through extraction, classification and linking."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request, UploadFile
from fastapi.responses import JSONResponse

from procintel.auth import service
from procintel.intake import extract, process, store

router = APIRouter()


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
    user = getattr(request.state, "user", None)
    up = store.save(file.filename, content, fmt, service.pseudonym(user["username"]) if user else None)
    if up["status"] == "received":
        background.add_task(process.run, up["upload_id"])   # seconds: extraction, classification, linking
    return up


@router.get("/intake/uploads")
def get_uploads(limit: int = 50) -> dict:
    return {"uploads": store.recent(max(1, min(limit, 200))), "formats": sorted(extract.READERS),
            "maxMb": extract.MAX_BYTES // 2**20}


@router.get("/intake/uploads/{upload_id}")
def get_upload(upload_id: str) -> dict:
    up = store.get(upload_id)
    return up if up else JSONResponse({"error": "no such upload"}, status_code=404)
