"""Photos and videos attached to a project (or one of its packages) as evidence, e.g. site visits.

The uploader names the project, and optionally the package (bid reference), the file belongs to: nothing is guessed
from the file. The file goes to blob storage under media/; its record (table media in the pipeline store) holds the
link, a caption, when it was taken, who uploaded it, and whether it is synthetic demo material (shown as such).
Signed-in planners see the media of any project, like the evidence; the uploader or an admin removes it.

    save(...) -> dict      list_for(project_ids) -> [dict]      get(media_id) -> dict | None      remove(media_id)
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from procintel.core import blob, db
from procintel.pipeline import store as pipeline_store

PREFIX = "media"
TYPES = {   # extension -> content type; browsers play these without a plugin
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif",
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
}
MAX_BYTES = {"image": 20 * 2**20, "video": 200 * 2**20}
COLUMNS = ["media_id", "project_id", "package_ref", "kind", "content_type", "filename", "size", "sha256", "path",
           "caption", "taken_on", "uploaded_by", "uploaded_at", "synthetic"]


def connect(db_path: Path | None = None):
    con = pipeline_store.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS media (media_id VARCHAR, project_id VARCHAR, package_ref VARCHAR,
                   kind VARCHAR, content_type VARCHAR, filename VARCHAR, size BIGINT, sha256 VARCHAR, path VARCHAR,
                   caption VARCHAR, taken_on DATE, uploaded_by VARCHAR, uploaded_at TIMESTAMP, synthetic BOOLEAN)""")
    return con


def type_of(filename: str) -> tuple[str, str] | None:
    """(kind image|video, content type) for an accepted file name, else None."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ct = TYPES.get(ext)
    return (ct.split("/")[0], ct) if ct else None


def known_project(project_id: str) -> bool:
    con = db.connect(read_only=True)
    try:
        return bool(con.execute("SELECT 1 FROM projects WHERE project_id = ?", [project_id]).fetchone())
    finally:
        con.close()


def _row(r: tuple) -> dict:
    d = dict(zip(COLUMNS, r))
    return {"id": d["media_id"], "projectId": d["project_id"], "packageRef": d["package_ref"], "kind": d["kind"],
            "contentType": d["content_type"], "filename": d["filename"], "size": d["size"], "caption": d["caption"],
            "takenOn": d["taken_on"].isoformat() if d["taken_on"] else None, "uploadedBy": d["uploaded_by"],
            "uploadedAt": d["uploaded_at"].isoformat() + "Z", "synthetic": bool(d["synthetic"]),
            "url": f"/media/{d['media_id']}/file"}


def save(filename: str, content: bytes, project_id: str, uploaded_by: str | None, package_ref: str | None = None,
         caption: str | None = None, taken_on: date | None = None, synthetic: bool = False,
         db_path: Path | None = None) -> dict:
    kind, ct = type_of(filename) or (None, None)
    if kind is None:
        raise ValueError(f"unsupported file type; accepted: {', '.join(sorted(TYPES))}")
    if len(content) > MAX_BYTES[kind]:
        raise ValueError(f"the {kind} is larger than {MAX_BYTES[kind] // 2**20} MB")
    if not content:
        raise ValueError("the file is empty")
    mid = uuid.uuid4().hex[:12]
    key = f"{PREFIX}/{mid}.{filename.rsplit('.', 1)[-1].lower()}"
    blob.store().put(key, content)
    con = connect(db_path)
    try:
        con.execute(f"INSERT INTO media VALUES ({', '.join('?' * len(COLUMNS))})",
                    [mid, project_id, (package_ref or "").strip() or None, kind, ct, filename, len(content),
                     hashlib.sha256(content).hexdigest(), key, (caption or "").strip()[:500] or None, taken_on,
                     uploaded_by, datetime.now(timezone.utc).replace(tzinfo=None), synthetic])
    finally:
        con.close()
    return get(mid, db_path)


def get(media_id: str, db_path: Path | None = None) -> dict | None:
    con = connect(db_path)
    try:
        r = con.execute(f"SELECT {', '.join(COLUMNS)} FROM media WHERE media_id = ?", [media_id]).fetchone()
        return _row(r) if r else None
    finally:
        con.close()


def path_of(media_id: str, db_path: Path | None = None) -> tuple[str, str] | None:
    """(blob key, content type) of a media file."""
    con = connect(db_path)
    try:
        r = con.execute("SELECT path, content_type FROM media WHERE media_id = ?", [media_id]).fetchone()
        return (r[0], r[1]) if r else None
    finally:
        con.close()


def list_for(project_ids: list[str], db_path: Path | None = None, limit: int = 60) -> list[dict]:
    """The media of these projects, newest first (by when taken, then uploaded)."""
    if not project_ids:
        return []
    con = connect(db_path)
    try:
        rows = con.execute(f"""SELECT {', '.join(COLUMNS)} FROM media WHERE project_id IN (SELECT unnest(?))
                               ORDER BY taken_on DESC NULLS LAST, uploaded_at DESC LIMIT ?""", [project_ids, limit]).fetchall()
        return [_row(r) for r in rows]
    finally:
        con.close()


def remove(media_id: str, db_path: Path | None = None) -> bool:
    con = connect(db_path)
    try:
        r = con.execute("SELECT path FROM media WHERE media_id = ?", [media_id]).fetchone()
        if not r:
            return False
        blob.store().delete(r[0])
        con.execute("DELETE FROM media WHERE media_id = ?", [media_id])
        return True
    finally:
        con.close()
