"""An upload through its stages: extract the text, classify it, link it, and for a completion report linked to a known
project add it to the evidence corpus (the documents table, doc_id "upload-<id>"; kept by the weekly refresh) and log
an Upload.ingested event, which the rules turn into cutting, indexing and checking its passages (a pipeline_batch job,
run when the app is idle). The first three stages take seconds and run right after the upload. remove() takes an upload
back out: its file is deleted and its report leaves the evidence the same way (Upload.removed); its record stays, marked
removed, as history."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from procintel.core import blob, db
from procintel.intake import classify, extract, link, ocr, store
from procintel.pipeline import detect
from procintel.pipeline import store as pipeline_store

ICR_TYPE = "Implementation Completion and Results Report"   # as the World Bank documents API names them
MIN_CHARS = 500     # less text than this: a scan without a text layer, or an empty file


def _pages(up: dict) -> tuple[list[str], int]:
    """(pages, how many were read by OCR)."""
    # the path column holds a blob key; uploads from before object storage hold an absolute file path
    if up["path"].startswith("/"):
        return extract.pages_ocr(Path(up["path"]), up["format"])
    with blob.local_copy(up["path"], suffix=f".{up['format']}") as path:
        return extract.pages_ocr(path, up["format"])


def run(upload_id: str, db_path: Path | None = None, jobs_db: Path | None = None, trusted: bool = True) -> dict:
    """trusted: uploaded by an admin. A planner's completion report would change everyone's evidence, so it waits for
    an admin (status awaiting_approval, then approve())."""
    up = store.get(upload_id, db_path)
    if up is None or up["status"] != "received":
        return up
    try:
        pages, scanned = _pages(up)
    except Exception as e:
        store.advance(upload_id, "extract", f"could not read the file: {e}", "failed", db_path, error=str(e)[:500])
        return store.get(upload_id, db_path)
    text = "\n\n".join(pages).strip()
    if len(text) < MIN_CHARS:
        why = ("even after OCR" if scanned else "a scan needs OCR, which is not available here" if not ocr.engine()
               else "too little text")
        store.advance(upload_id, "extract", f"{len(text)} characters of text ({why}); review by hand", "needs_review",
                      db_path)
        return store.get(upload_id, db_path)
    store.advance(upload_id, "extract", f"{len(pages)} page{'s' if len(pages) != 1 else ''}, {len(text):,} characters"
                  + (f"; {scanned} scanned page{'s' if scanned != 1 else ''} read by OCR ({ocr.engine()})" if scanned
                     else ""), "extracted", db_path)

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
                  f"{', '.join(links['countries']) or 'none'}; {len(links['packages'])} package(s) by bid reference, "
                  f"{len(links['firms'])} firm(s) by name", "linked", db_path, links=links)

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
    if not trusted:
        store.advance(upload_id, "done", "a completion report about a tracked project; it joins the evidence everyone "
                      "searches once an admin adds it", "awaiting_approval", db_path)
        return store.get(upload_id, db_path)
    return _add(up, text, known, db_path, jobs_db)


def approve(upload_id: str, db_path: Path | None = None, jobs_db: Path | None = None) -> dict | None:
    """An admin adds a waiting completion report to the evidence: one a planner uploaded, or one the decision model
    alone called a completion report. Raises ValueError when the upload cannot join the evidence."""
    up = store.get(upload_id, db_path)
    if up is None:
        return None
    if up["status"] not in ("awaiting_approval", "needs_review") or up["doc_type"] != "completion_report":
        raise ValueError("only a completion report waiting for review can be added to the evidence")
    known = [p["id"] for p in (up["links"] or {}).get("projects", []) if p["known"]]
    if not known:
        raise ValueError("it names no tracked project, so it cannot be linked to the evidence")
    text = "\n\n".join(_pages(up)[0]).strip()
    store.advance(upload_id, "approved", "added by an admin", None, db_path)
    return _add(up, text, known, db_path, jobs_db)


def _add(up: dict, text: str, known: list[str], db_path: Path | None, jobs_db: Path | None) -> dict:
    upload_id = up["upload_id"]
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


def remove(upload_id: str, db_path: Path | None = None, jobs_db: Path | None = None) -> dict | None:
    """Delete an upload's file and, if it was added to the evidence, its document (passages, vectors and tags follow
    when the rules re-cut and re-index). Returns the upload as it now stands, or None when there is no such upload."""
    up = store.get(upload_id, db_path)
    if up is None or up["status"] == "removed":
        return up
    notes = []
    if up["doc_id"]:
        con = db.connect()
        try:
            con.execute("DELETE FROM documents WHERE doc_id = ?", [up["doc_id"]])
        finally:
            con.close()
        batch = pipeline_store.new_batch()
        pipeline_store.log_derived(batch, [{"type": "Upload.removed", "key": up["doc_id"]}], db_path)
        job = detect.queue_batch(batch, "removed upload", jobs_db, priority="high")
        notes.append(f"{up['doc_id']} taken out of the evidence" + (f"; its passages are removed by job {job}" if job else ""))
    if up["path"]:
        if up["path"].startswith("/"):
            Path(up["path"]).unlink(missing_ok=True)   # uploads from before object storage
        else:
            blob.store().delete(up["path"])
        notes.append("file deleted")
    store.advance(upload_id, "removed", "; ".join(notes) or "nothing stored to delete (a duplicate)", "removed",
                  db_path, path=None)
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
