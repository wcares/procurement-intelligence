"""The image of a figure cited as evidence (procintel.ingestion.doc_figures keeps them in blob storage)."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from procintel.core import blob
from procintel.ingestion import doc_figures

router = APIRouter()
_DOC = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


@router.get("/figures/{doc_id}/{n}")
def figure_image(doc_id: str, n: int) -> Response:
    """The PNG of figure n of a report. The ids are checked before they become a storage key."""
    if not _DOC.match(doc_id) or not 0 <= n < 1000:
        raise HTTPException(404, "no such figure")
    data = blob.store().get(doc_figures.image_key(doc_id, n))
    if data is None:
        raise HTTPException(404, "no such figure")
    return Response(data, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
