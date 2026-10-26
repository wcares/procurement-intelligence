"""An upload through its stages: extract the text, classify it, link it, and for a completion report linked to a known
project add it to the evidence corpus (the documents table, doc_id "upload-<id>"; kept by the weekly refresh) and log
an Upload.ingested event, which the rules turn into cutting, indexing and checking its passages (a pipeline_batch job,
run when the app is idle). The first three stages take seconds and run right after the upload."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from procintel.core import db
from procintel.intake import classify, extract, link, store
from procintel.pipeline import detect
from procintel.pipeline import store as pipeline_store

ICR_TYPE = "Implementation Completion and Results Report"   # as the World Bank documents API names them
MIN_CHARS = 500     # less text than this: a scan without a text layer, or an empty file


def run(upload_id: str, db_path: Path | None = None, jobs_db: Path | None = None) -> dict:
    up = store.get(upload_id, db_path)
    if up is None or up["status"] != "received":
        return up
    try:
        pages = extract.pages(Path(up["path"]), up["format"])
    except Exception as e:
        store.advance(upload_id, "extract", f"could not read the file: {e}", "failed", db_path, error=str(e)[:500])
        return store.get(upload_id, db_path)
    text = "\n\n".join(pages).strip()
    if len(text) < MIN_CHARS:
        store.advance(upload_id, "extract", f"{len(text)} characters of text: a scan needs OCR, which is not "
                      "available; review by hand", "needs_review", db_path)
        return store.get(upload_id, db_path)
    store.advance(upload_id, "extract", f"{len(pages)} page{'s' if len(pages) != 1 else ''}, {len(text):,} characters",
                  "extracted", db_path)

    kind = classify.classify(text)
    sure = kind["method"] != "review"
    how = ("from its title" + kind["method"][len("title"):] if kind["titled"]
           else kind["method"] + (f", {kind['confidence']:.0%}" if kind["confidence"] is not None else ""))
    store.advance(upload_id, "classify", f"{kind['type'].replace('_', ' ')} ({how})",
                  "classified" if sure else "needs_review", db_path,
                  doc_type=kind["type"], type_confidence=kind["confidence"])
    if not sure:
        return store.get(upload_id, db_path)

    links = link.find(text)
    known = [p["id"] for p in links["projects"] if p["known"]]
    store.advance(upload_id, "link", f"{len(links['projects'])} project id(s), {len(known)} known; countries: "
                  f"{', '.join(links['countries']) or 'none'}", "linked", db_path, links=links)

    if kind["type"] == "completion_report" and not kind["titled"]:
        store.advance(upload_id, "done", "a completion report by the decision model only (no such title in the "
                      "opening); confirm by hand before it is added to the evidence", "needs_review", db_path)
        return store.get(upload_id, db_path)
    if kind["type"] != "completion_report":
        store.advance(upload_id, "done", "kept and linked; only completion reports are added to the evidence searched "
                      "today", "kept", db_path)
        return store.get(upload_id, db_path)
    if not known:
        store.advance(upload_id, "done", "a completion report, but no project id in it matches a tracked project; "
                      "review by hand", "needs_review", db_path)
        return store.get(upload_id, db_path)

    doc_id = f"upload-{upload_id}"
    title = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 10), up["filename"])[:200]
    _add_document(doc_id, ",".join(known), title, text)
    batch = pipeline_store.new_batch()
    pipeline_store.log_derived(batch, [{"type": "Upload.ingested", "key": doc_id}], db_path)
    job = detect.queue_batch(batch, "uploaded report(s)", jobs_db, priority="high")
    store.advance(upload_id, "add", f"added to the evidence as {doc_id}; its passages are cut and indexed by job "
                  f"{job} (runs when the app is next idle)" if job else f"added as {doc_id}; no rule asked for indexing",
                  "added", db_path, doc_id=doc_id)
    return store.get(upload_id, db_path)


def _add_document(doc_id: str, project_ids: str, title: str, text: str) -> None:
    row = pd.DataFrame([{"doc_id": doc_id, "project_id": project_ids, "doc_type": ICR_TYPE,
                         "doc_date": pd.Timestamp.now(tz="UTC"), "title": title, "pdf_url": None, "txt_url": None,
                         "text": text}])
    con = db.connect()
    try:
        con.execute("DELETE FROM documents WHERE doc_id = ?", [doc_id])
        con.execute("INSERT INTO documents BY NAME SELECT * FROM row")
    finally:
        con.close()
