"""Project photos and videos as evidence answers can cite: each media item with a caption becomes a document of type
"Project media" (doc_id media-<id>) whose one passage (kind "media") says what the uploader wrote it shows, for which
project and package, and when it was taken. The picture itself is shown with the citation.

The text is the uploader's caption, not a reading of the image: a citation of a photo says "the uploader says this
shows ...", and a synthetic demo item says so in its text and is labelled on screen. Synthetic items are left out of the
evidence when PROCINTEL_MEDIA_SYNTHETIC_EVIDENCE=off.

    sync() -> {"added": n, "removed": n}     brings the documents table in line with the media table
"""
from __future__ import annotations

import os

import pandas as pd

from procintel.core import db
from procintel.intake import media

MEDIA_TYPE = "Project media"
PREFIX = "media-"


def doc_id(media_id: str) -> str:
    return f"{PREFIX}{media_id}"


def media_id(doc: str) -> str | None:
    return doc[len(PREFIX):] if doc.startswith(PREFIX) else None


def text_of(m: dict) -> str:
    what = "Video" if m["kind"] == "video" else "Photo"
    where = f"project {m['projectId']}" + (f", package {m['packageRef']}" if m["packageRef"] else "")
    when = f", taken {m['takenOn']}" if m["takenOn"] else ""
    demo = " This is a SYNTHETIC DEMO item made up for a demonstration, not real evidence." if m["synthetic"] else ""
    return f"{what} attached to {where}{when}. The uploader describes it as: {m['caption']}.{demo}"


def _wanted() -> list[dict]:
    synthetic = os.environ.get("PROCINTEL_MEDIA_SYNTHETIC_EVIDENCE", "on").strip().lower() != "off"
    con = media.connect()
    try:
        ids = [r[0] for r in con.execute("SELECT media_id FROM media WHERE coalesce(caption, '') <> ''").fetchall()]
    finally:
        con.close()
    items = [media.get(i) for i in ids]
    return [m for m in items if m and (synthetic or not m["synthetic"])]


def sync() -> dict:
    """Add a document for every captioned media item not yet in the evidence (or whose text changed) and remove those
    whose media item is gone. Returns counts; nothing is written when nothing changed."""
    want = {doc_id(m["id"]): m for m in _wanted()}
    con = db.connect()
    try:
        have = dict(con.execute("SELECT doc_id, text FROM documents WHERE doc_id LIKE 'media-%'").fetchall())
        gone = [d for d in have if d not in want]
        new = [m for d, m in want.items() if have.get(d) != text_of(m)]
        for d in gone + [doc_id(m["id"]) for m in new]:
            con.execute("DELETE FROM documents WHERE doc_id = ?", [d])
        if new:
            rows = pd.DataFrame([{"doc_id": doc_id(m["id"]), "project_id": m["projectId"], "doc_type": MEDIA_TYPE,
                                  "doc_date": pd.Timestamp(m["takenOn"] or m["uploadedAt"][:10], tz="UTC"),
                                  "title": f"{'Video' if m['kind'] == 'video' else 'Photo'}: {m['caption']}"[:200],
                                  "pdf_url": None, "txt_url": None, "text": text_of(m)} for m in new])
            con.execute("INSERT INTO documents BY NAME SELECT * FROM rows")
        return {"added": len(new), "removed": len(gone)}
    finally:
        con.close()


def apply_and_queue(jobs_db=None) -> str | None:
    """sync(), then queue the pipeline batch that cuts and indexes the changed media documents (like an upload)."""
    from procintel.pipeline import detect, store as pipeline_store
    changed = sync()
    if not (changed["added"] or changed["removed"]):
        return None
    batch = pipeline_store.new_batch()
    pipeline_store.log_derived(batch, [{"type": "Upload.ingested", "key": "media"}])
    return detect.queue_batch(batch, "project media", jobs_db, priority="high")
