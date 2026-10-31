"""The tables of each report, read from its PDF and kept in `doc_table` (one row per table, markdown).

The text export the pipeline cuts passages from (`txturl`) has no table structure, so the PDF is read as well:
fetched reports from `documents.pdf_url` (downloaded once, kept in blob storage under pdfs/), uploads from the file
they were stored as. procintel.ingestion.chunk then adds each table as a passage of kind "grid".

    python -m procintel.ingestion.doc_tables [limit]        # read the reports not read yet (default: all)

`doc_table_read` records which report was read from which PDF address, so a report with no tables is not downloaded
again, and a changed address is read again.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

from procintel.core import blob, db, paths
from procintel.ingestion import pdf_tables

DB_PATH = paths.DB_PATH
PDF_PREFIX = "pdfs"        # key prefix in procintel.core.blob
UA = {"User-Agent": "procintel-prototype/0.1 (research)"}
MIN_PDF_BYTES = 1000


def ensure(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS doc_table (doc_id VARCHAR, tseq INTEGER, page INTEGER, caption VARCHAR,
                   n_rows INTEGER, markdown VARCHAR)""")
    con.execute("CREATE TABLE IF NOT EXISTS doc_table_read (doc_id VARCHAR, source VARCHAR, n_tables INTEGER, read_at TIMESTAMP)")


def pdf_key(doc_id: str) -> str:
    return f"{PDF_PREFIX}/{doc_id}.pdf"


def fetch_pdf(doc_id: str, url: str, attempts: int = 3) -> str:
    """Download the PDF once and keep it in blob storage; returns its key. Raises RuntimeError when it cannot be had."""
    key = pdf_key(doc_id)
    if blob.store().get(key) is not None:
        return key
    last: Exception | None = None
    for i in range(attempts):
        try:
            r = requests.get(url, headers=UA, timeout=120)
            r.raise_for_status()
            if len(r.content) < MIN_PDF_BYTES or not r.content.startswith(b"%PDF"):
                raise ValueError("not a PDF")
            blob.store().put(key, r.content)
            return key
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"PDF of {doc_id} not fetched: {url}") from last


def save(con, doc_id: str, source: str, found: list[pdf_tables.PdfTable]) -> int:
    """Replace the report's tables with `found`; returns how many."""
    ensure(con)
    con.execute("DELETE FROM doc_table WHERE doc_id = ?", [doc_id])
    con.execute("DELETE FROM doc_table_read WHERE doc_id = ?", [doc_id])
    for i, t in enumerate(found):
        con.execute("INSERT INTO doc_table VALUES (?, ?, ?, ?, ?, ?)", [doc_id, i, t.page, t.caption, len(t.rows), t.markdown])
    con.execute("INSERT INTO doc_table_read VALUES (?, ?, ?, now())", [doc_id, source, len(found)])
    return len(found)


def read_key(con, doc_id: str, key: str, source: str | None = None) -> int:
    """Read the tables of the PDF stored under blob `key` for report `doc_id` (an upload, or a fetched report)."""
    with blob.local_copy(key, suffix=".pdf") as path:
        found = pdf_tables.tables(path)
    return save(con, doc_id, source or key, found)


def pending(con) -> list[tuple[str, str]]:
    """(doc_id, pdf_url) of reports with a PDF address that has not been read from that address."""
    ensure(con)
    return con.execute("""SELECT d.doc_id, d.pdf_url FROM documents d
                          LEFT JOIN doc_table_read r ON r.doc_id = d.doc_id AND r.source = d.pdf_url
                          WHERE d.pdf_url IS NOT NULL AND r.doc_id IS NULL ORDER BY d.doc_id""").fetchall()


def build(db_path: Path = DB_PATH, limit: int | None = None) -> dict:
    """Read the tables of every fetched report not read yet. A PDF that cannot be fetched or read is counted and left
    for the next run; it never stops the others."""
    con = db.connect(db_path)
    try:
        todo = pending(con)[:limit]
        done = tables = failed = 0
        for doc_id, url in todo:
            try:
                key = fetch_pdf(doc_id, url)
                tables += read_key(con, doc_id, key, source=url)
                done += 1
            except Exception as e:  # noqa: BLE001 - one bad PDF must not stop the batch
                failed += 1
                print(f"doc_tables: {doc_id}: {type(e).__name__}: {e}")
        return {"read": done, "tables": tables, "failed": failed, "left": len(pending(con))}
    finally:
        con.close()


def for_chunks(con) -> dict[str, list[dict]]:
    """doc_id -> its tables in page order (page, caption, markdown, n_rows), for the chunk build; {} before any read."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'doc_table'").fetchone():
        return {}
    out: dict[str, list[dict]] = {}
    for doc_id, page, caption, n_rows, md in con.execute(
            "SELECT doc_id, page, caption, n_rows, markdown FROM doc_table ORDER BY doc_id, page, tseq").fetchall():
        out.setdefault(doc_id, []).append({"page": page, "caption": caption, "n_rows": n_rows, "markdown": md})
    return out


if __name__ == "__main__":
    print(build(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None))
