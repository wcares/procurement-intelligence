"""User feedback on answers and assessments, kept with the exact response the user saw.

Stored in its own DuckDB file (data/feedback.duckdb), not in the main database: DuckDB allows one writing process per
file, and a running server writing to the main file would block the build commands (chunk, embed, tag, predict).
Each call opens and closes its own connection, so the file is never held between requests.

  response_log   every /ask and /assess response: id, kind, request, response, time
  feedback       ratings on a response: useful / not_useful / bad_citation (naming the citation), optional comment
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from procintel import db, paths

DB_PATH = paths.FEEDBACK_DB
RATINGS = ("useful", "not_useful", "bad_citation")
_LOCK = threading.Lock()  # one writer at a time within the server process


def _connect(db_path: Path | None) -> duckdb.DuckDBPyConnection:
    db_path = db_path or DB_PATH  # resolved per call, so tests can point DB_PATH at a temporary file
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(db_path)
    con.execute("""CREATE TABLE IF NOT EXISTS response_log (
        response_id VARCHAR PRIMARY KEY, kind VARCHAR, request JSON, response JSON, created_at TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS feedback (
        feedback_id VARCHAR PRIMARY KEY, response_id VARCHAR, rating VARCHAR, citation_id VARCHAR, comment VARCHAR,
        created_at TIMESTAMP)""")
    return con


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def log_response(kind: str, request: dict, response: dict, db_path: Path | None = None) -> str:
    """Store a response and return its id (also put into response['meta']['responseId'])."""
    rid = uuid.uuid4().hex
    response["meta"]["responseId"] = rid
    with _LOCK:
        con = _connect(db_path)
        try:
            con.execute("INSERT INTO response_log VALUES (?, ?, ?, ?, ?)",
                        [rid, kind, json.dumps(request), json.dumps(response), _now()])
        finally:
            con.close()
    return rid


def _cited_ids(response: dict) -> set[str]:
    cites = response.get("citations") or [p["citation"] for p in response.get("precedents") or []]
    return {c["id"] for c in cites}


def add(response_id: str, rating: str, citation_id: str | None = None, comment: str | None = None,
        db_path: Path | None = None) -> str:
    """Store one rating. ValueError for an unknown response, a citation the response did not show, or a bad rating."""
    if rating not in RATINGS:
        raise ValueError(f"rating must be one of {RATINGS}")
    if rating == "bad_citation" and not citation_id:
        raise ValueError("bad_citation needs the citation id")
    with _LOCK:
        con = _connect(db_path)
        try:
            row = con.execute("SELECT response FROM response_log WHERE response_id = ?", [response_id]).fetchone()
            if row is None:
                raise ValueError("unknown response id")
            if citation_id and citation_id not in _cited_ids(json.loads(row[0])):
                raise ValueError("that citation was not part of this response")
            fid = uuid.uuid4().hex
            con.execute("INSERT INTO feedback VALUES (?, ?, ?, ?, ?, ?)",
                        [fid, response_id, rating, citation_id, (comment or "").strip()[:1000] or None, _now()])
        finally:
            con.close()
    return fid


def summary(db_path: Path | None = None) -> dict:
    """Counts by kind and rating, and the most flagged citations (for the evaluation report)."""
    if not (db_path or DB_PATH).exists():
        return {"responses": 0, "ratings": [], "flagged_citations": []}
    with _LOCK:
        con = _connect(db_path)
        try:
            return {
                "responses": con.execute("SELECT count(*) FROM response_log").fetchone()[0],
                "ratings": con.execute("""SELECT l.kind, f.rating, count(*) FROM feedback f JOIN response_log l USING (response_id)
                                          GROUP BY ALL ORDER BY 1, 2""").fetchall(),
                "flagged_citations": con.execute("""SELECT citation_id, count(*) n FROM feedback WHERE rating = 'bad_citation'
                                                    GROUP BY 1 ORDER BY n DESC LIMIT 20""").fetchall(),
            }
        finally:
            con.close()
