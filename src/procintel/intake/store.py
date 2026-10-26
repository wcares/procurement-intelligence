"""Uploaded files and how far each got: stored by key under "uploads/" (procintel.core.blob: the data folder or object
storage), recorded in the pipeline store (table upload),
with every stage it passed and what it found. The same content twice (same SHA-256) is recorded as a duplicate of the
first and not processed again."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from procintel.core import blob
from procintel.pipeline import store as pipeline_store

UPLOAD_PREFIX = "uploads"   # key prefix in procintel.core.blob; the path column holds the key
COLUMNS = ["upload_id", "filename", "format", "size", "sha256", "path", "uploaded_by", "uploaded_at", "status",
           "stages", "doc_type", "type_confidence", "links", "doc_id", "error"]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def connect(db_path: Path | None = None):
    con = pipeline_store.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS upload (upload_id VARCHAR, filename VARCHAR, format VARCHAR,
                   size BIGINT, sha256 VARCHAR, path VARCHAR, uploaded_by VARCHAR, uploaded_at TIMESTAMP,
                   status VARCHAR, stages VARCHAR, doc_type VARCHAR, type_confidence DOUBLE, links VARCHAR,
                   doc_id VARCHAR, error VARCHAR)""")
    return con


def _row(r: tuple) -> dict:
    d = dict(zip(COLUMNS, r))
    d["stages"] = json.loads(d["stages"] or "[]")
    d["links"] = json.loads(d["links"]) if d["links"] else None
    d["uploaded_at"] = d["uploaded_at"].isoformat() + "Z"
    return d


def save(filename: str, content: bytes, fmt: str, uploaded_by: str | None, db_path: Path | None = None) -> dict:
    """Store the file and record it; a repeat of earlier content is recorded as a duplicate (status 'duplicate')."""
    digest = hashlib.sha256(content).hexdigest()
    con = connect(db_path)
    try:
        first = con.execute("SELECT upload_id FROM upload WHERE sha256 = ? AND status <> 'duplicate' "
                            "ORDER BY uploaded_at LIMIT 1", [digest]).fetchone()
        uid = uuid.uuid4().hex[:12]
        key = f"{UPLOAD_PREFIX}/{uid}.{fmt}"      # procintel.core.blob: data folder or object storage
        if not first:
            blob.store().put(key, content)
        status = "duplicate" if first else "received"
        stage = {"stage": "received", "at": _now().isoformat() + "Z",
                 "detail": f"same content as upload {first[0]}" if first else f"{len(content):,} bytes"}
        con.execute(f"INSERT INTO upload ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                    [uid, filename, fmt, len(content), digest, None if first else key, uploaded_by, _now(),
                     status, json.dumps([stage]), None, None, None, None, None])
    finally:
        con.close()
    return get(uid, db_path)


def get(upload_id: str, db_path: Path | None = None) -> dict | None:
    con = connect(db_path)
    try:
        r = con.execute(f"SELECT {', '.join(COLUMNS)} FROM upload WHERE upload_id = ?", [upload_id]).fetchone()
        return _row(r) if r else None
    finally:
        con.close()


def recent(limit: int = 50, db_path: Path | None = None, uploaded_by: str | None = None) -> list[dict]:
    """Newest first; uploaded_by (a pseudonym) keeps one person's uploads only."""
    con = connect(db_path)
    try:
        where, args = ("WHERE uploaded_by = ? ", [uploaded_by]) if uploaded_by else ("", [])
        return [_row(r) for r in con.execute(f"SELECT {', '.join(COLUMNS)} FROM upload {where}ORDER BY uploaded_at DESC "
                                             "LIMIT ?", args + [limit]).fetchall()]
    finally:
        con.close()


def advance(upload_id: str, stage: str, detail: str, status: str | None = None, db_path: Path | None = None,
            **fields) -> None:
    """Record a stage passed (with what it found) and set the status and any of doc_type, type_confidence, links,
    doc_id, error."""
    con = connect(db_path)
    try:
        stages = json.loads(con.execute("SELECT stages FROM upload WHERE upload_id = ?", [upload_id]).fetchone()[0])
        stages.append({"stage": stage, "at": _now().isoformat() + "Z", "detail": detail})
        sets = {"stages": json.dumps(stages), **({"status": status} if status else {}),
                **{k: json.dumps(v) if k == "links" else v for k, v in fields.items()}}
        con.execute(f"UPDATE upload SET {', '.join(f'{k} = ?' for k in sets)} WHERE upload_id = ?",
                    [*sets.values(), upload_id])
    finally:
        con.close()
