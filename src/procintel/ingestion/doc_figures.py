"""The figures of each report, read from its PDF and kept in `doc_figure` (one row per figure) with the image in blob
storage under figures/<doc_id>/<n>.png.

Same shape as procintel.ingestion.doc_tables, which already downloaded the PDFs. A figure's text is its caption and,
when a vision model is configured (procintel.ingestion.figure_text), a machine description; procintel.ingestion.chunk
turns each figure that has text into a passage of kind "figure".

    python -m procintel.ingestion.doc_figures [limit]            # read the reports not read yet
    python -m procintel.ingestion.doc_figures describe [limit]   # describe figures that have no description yet
"""
from __future__ import annotations

import sys
from pathlib import Path

from procintel.core import blob, db, paths
from procintel.ingestion import doc_tables, figure_text, figures

DB_PATH = paths.DB_PATH
IMAGE_PREFIX = "figures"


def ensure(con) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS doc_figure (doc_id VARCHAR, fseq INTEGER, page INTEGER, caption VARCHAR,
                   image_key VARCHAR, description VARCHAR, described_by VARCHAR)""")
    con.execute("CREATE TABLE IF NOT EXISTS doc_figure_read (doc_id VARCHAR, source VARCHAR, n_figures INTEGER, read_at TIMESTAMP)")


def image_key(doc_id: str, n: int) -> str:
    return f"{IMAGE_PREFIX}/{doc_id}/{n}.png"


def save(con, doc_id: str, source: str, found: list[figures.PdfFigure]) -> int:
    """Replace the report's figures (rows and images) with `found`; returns how many. Descriptions are kept for a
    figure whose page and caption are unchanged."""
    ensure(con)
    old = con.execute("SELECT fseq, page, caption, description, described_by, image_key FROM doc_figure WHERE doc_id = ?",
                      [doc_id]).fetchall()
    kept = {(p, c): (d, by) for _, p, c, d, by, _ in old if d}
    for *_, key in old:
        blob.store().delete(key)
    con.execute("DELETE FROM doc_figure WHERE doc_id = ?", [doc_id])
    con.execute("DELETE FROM doc_figure_read WHERE doc_id = ?", [doc_id])
    for i, f in enumerate(found):
        key = image_key(doc_id, i)
        blob.store().put(key, f.png)
        d, by = kept.get((f.page, f.caption), (None, None))
        con.execute("INSERT INTO doc_figure VALUES (?, ?, ?, ?, ?, ?, ?)", [doc_id, i, f.page, f.caption, key, d, by])
    con.execute("INSERT INTO doc_figure_read VALUES (?, ?, ?, now())", [doc_id, source, len(found)])
    return len(found)


def read_key(con, doc_id: str, key: str, source: str | None = None) -> int:
    """Read the figures of the PDF stored under blob `key` for report `doc_id` (an upload, or a fetched report)."""
    with blob.local_copy(key, suffix=".pdf") as path:
        found = figures.figures(path)
    return save(con, doc_id, source or key, found)


def pending(con) -> list[tuple[str, str]]:
    ensure(con)
    return con.execute("""SELECT d.doc_id, d.pdf_url FROM documents d
                          LEFT JOIN doc_figure_read r ON r.doc_id = d.doc_id AND r.source = d.pdf_url
                          WHERE d.pdf_url IS NOT NULL AND r.doc_id IS NULL ORDER BY d.doc_id""").fetchall()


def build(db_path: Path = DB_PATH, limit: int | None = None) -> dict:
    """Read the figures of every fetched report not read yet (database open only to list and to save)."""
    con = db.connect(db_path)
    try:
        todo = pending(con)[:limit]
    finally:
        con.close()
    done = n = failed = 0
    for doc_id, url in todo:
        try:
            key = doc_tables.fetch_pdf(doc_id, url)
            with blob.local_copy(key, suffix=".pdf") as path:
                found = figures.figures(path)
            con = db.connect(db_path)
            try:
                n += save(con, doc_id, url, found)
            finally:
                con.close()
            done += 1
        except Exception as e:  # noqa: BLE001 - one bad PDF must not stop the batch
            failed += 1
            print(f"doc_figures: {doc_id}: {type(e).__name__}: {e}", flush=True)
    con = db.connect(db_path)
    try:
        return {"read": done, "figures": n, "failed": failed, "left": len(pending(con))}
    finally:
        con.close()


def describe_pending(db_path: Path = DB_PATH, limit: int | None = None) -> dict:
    """Describe the figures without a description with the configured vision model (nothing when none is set)."""
    if not figure_text.configured():
        return {"described": 0, "failed": 0, "note": "PROCINTEL_VISION_MODEL is not set"}
    con = db.connect(db_path)
    try:
        ensure(con)
        todo = con.execute("""SELECT doc_id, fseq, caption, image_key FROM doc_figure
                              WHERE coalesce(description, '') = '' ORDER BY doc_id, fseq""").fetchall()[:limit]
    finally:
        con.close()
    done = failed = 0
    for doc_id, fseq, caption, key in todo:
        try:
            png = blob.store().get(key)
            text = figure_text.describe(png, caption) if png else ""
            if text:
                con = db.connect(db_path)
                try:
                    con.execute("UPDATE doc_figure SET description = ?, described_by = ? WHERE doc_id = ? AND fseq = ?",
                                [text, figure_text.model_name(), doc_id, fseq])
                finally:
                    con.close()
                done += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"doc_figures: describe {doc_id}/{fseq}: {type(e).__name__}: {e}", flush=True)
    return {"described": done, "failed": failed}


def index_of(con, doc_id: str, page: int, caption: str | None) -> int | None:
    """The fseq of the figure of `doc_id` on `page` with this caption (None when there is none), for a citation's image."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'doc_figure'").fetchone():
        return None
    r = con.execute("""SELECT fseq FROM doc_figure WHERE doc_id = ? AND page = ? AND caption IS NOT DISTINCT FROM ?
                       ORDER BY fseq LIMIT 1""", [doc_id, page, caption]).fetchone()
    return r[0] if r else None


def for_chunks(con) -> dict[str, list[dict]]:
    """doc_id -> its figures in page order, for the chunk build; {} before any read."""
    if not con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'doc_figure'").fetchone():
        return {}
    out: dict[str, list[dict]] = {}
    for doc_id, fseq, page, caption, desc, by in con.execute(
            "SELECT doc_id, fseq, page, caption, description, described_by FROM doc_figure ORDER BY doc_id, page, fseq").fetchall():
        out.setdefault(doc_id, []).append({"fseq": fseq, "page": page, "caption": caption, "description": desc,
                                           "described_by": by})
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "describe":
        print(describe_pending(limit=int(args[1]) if len(args) > 1 else None))
    else:
        print(build(limit=int(args[0]) if args else None))
