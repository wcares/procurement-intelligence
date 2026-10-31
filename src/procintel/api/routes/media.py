"""Project media (procintel.intake.media): photos and videos attached to a project or package by planners."""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from procintel.api.routes.intake import _who
from procintel.core import blob
from procintel.intake import media

router = APIRouter()
_ID = re.compile(r"^[0-9a-f]{12}$")
_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


@router.post("/media")
async def post_media(request: Request, file: UploadFile, projectId: str = Form(...), packageRef: str = Form(""),
                     caption: str = Form(""), takenOn: str = Form("")) -> dict:
    kind = media.type_of(file.filename or "")
    if kind is None:
        return JSONResponse({"error": f"unsupported file type; accepted: {', '.join(sorted(media.TYPES))}"}, status_code=400)
    if not media.known_project(projectId.strip()):
        return JSONResponse({"error": f"unknown project {projectId!r}"}, status_code=400)
    try:
        taken = date.fromisoformat(takenOn) if takenOn else None
    except ValueError:
        return JSONResponse({"error": "takenOn must be a date (YYYY-MM-DD)"}, status_code=400)
    content = await file.read(media.MAX_BYTES[kind[0]] + 1)
    who, _ = _who(request)
    try:
        return media.save(file.filename, content, projectId.strip(), who, packageRef, caption, taken)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=413 if "larger" in str(e) else 400)


@router.get("/media")
def get_media(projectIds: str) -> dict:
    """Media of one or more projects (comma-separated ids), newest first."""
    ids = [p.strip() for p in projectIds.split(",") if p.strip()][:20]
    return {"items": media.list_for(ids), "accepted": sorted(media.TYPES)}


@router.get("/media/{media_id}/file")
def get_media_file(media_id: str, request: Request) -> Response:
    """The file itself; answers byte ranges so a video can be played and sought."""
    found = media.path_of(media_id) if _ID.match(media_id) else None
    data = blob.store().get(found[0]) if found else None
    if data is None:
        return JSONResponse({"error": "no such media"}, status_code=404)
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=86400"}
    m = _RANGE.match(request.headers.get("range", ""))
    if m and (m.group(1) or m.group(2)):
        n = len(data)
        start, end = (int(m.group(1)), int(m.group(2) or n - 1)) if m.group(1) else (n - int(m.group(2)), n - 1)
        if start >= n or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{n}"})
        end = min(end, n - 1)
        return Response(data[start:end + 1], status_code=206, media_type=found[1],
                        headers=headers | {"Content-Range": f"bytes {start}-{end}/{n}"})
    return Response(data, media_type=found[1], headers=headers)


@router.delete("/media/{media_id}")
def delete_media(media_id: str, request: Request) -> dict:
    item = media.get(media_id) if _ID.match(media_id) else None
    who, admin = _who(request)
    if not item or not (admin or (who and item["uploadedBy"] == who)):
        return JSONResponse({"error": "no such media"}, status_code=404)
    media.remove(media_id)
    return {"removed": media_id}
