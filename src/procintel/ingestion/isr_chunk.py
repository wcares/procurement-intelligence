"""Passages from an Implementation Status and Results Report (ISR), the supervision report filed every few months.

Layout facts this relies on (observed in ISR plain text from the documents API, 2026):
  - every page starts with a running header ("The World Bank ... Implementation Status & Results Report" and the
    project title with its id) and ends with a footer ("Apr 07, 2026 ... Page 3 of 9");
  - sections are numbered ("4. KEY ISSUES & STATUS", "4.1 Implementation Status and Key Decisions");
  - paragraphs are not numbered: they are separated by blank lines.

Kept: 3 overall ratings, 4 key issues and status, 5 the risk-rating table (fiduciary risk covers procurement). Left
out: 1 objective and 2 components (no supervision findings; they would only dilute search) and 6 onwards, the results
indicator tables, which pdf-to-text turns into interleaved columns. A passage's anchor is its section number and
paragraph ("4.1·2", or "4.1·2-3" when short paragraphs were joined), since there are no paragraph numbers to cite.
"""
from __future__ import annotations

import re

from procintel.ingestion.chunk import Chunk, _clean, _split_long, is_flat_table

KEEP = {"3", "4", "5"}
TABLES = {"3", "5"}     # rating tables: one passage each (their rows are separated by blank lines)
MERGE_UNDER = 600       # a paragraph shorter than this joins the next one in its subsection
_HEADING = re.compile(r"^\s{0,6}(\d{1,2}(?:\.\d{1,2})?)\.?\s+([A-Z][^.]{2,80})$")
_FOOTER = re.compile(r"^\s*[A-Z][a-z]{2} \d{1,2}, \d{4}\s+Page \d+ of \d+\s*$")
_HEADER = re.compile(r"^\s*The World Bank\b|Implementation Status &|\(P\d{6}\)\s*$")


def chunk_isr(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    top, section, number, para_n = None, "", "", 0
    buf: list[str] = []
    pending: list[tuple[int, str]] = []     # short paragraphs waiting to be joined

    def emit():
        if not pending:
            return
        body = " ".join(t for _, t in pending)
        first, last = pending[0][0], pending[-1][0]
        anchor = f"{number}·{first}" + (f"-{last}" if last != first else "")
        flat = top in TABLES or is_flat_table(body)
        for piece in _split_long(body):
            chunks.append(Chunk(section, anchor, "table" if flat else "text", piece))
        pending.clear()

    def flush():
        nonlocal para_n
        body = _clean(" ".join(buf))
        buf.clear()
        if not body or top not in KEEP or len(body) < 20:
            return
        para_n += 1
        pending.append((para_n, body))
        if top not in TABLES and sum(len(t) for _, t in pending) >= MERGE_UNDER:
            emit()

    for line in text.replace("\x0c", "\n").splitlines():
        if _FOOTER.match(line) or _HEADER.search(line):
            continue
        m = _HEADING.match(line)
        if m and (m.group(2).isupper() or "." in m.group(1)):
            flush()
            emit()
            number, title = m.group(1), m.group(2).strip()
            top = number.split(".")[0]
            parent = section.split(":")[0] if "." in number and section else ""
            section = f"{parent}: {title.title()}" if "." in number and parent else title.title()
            para_n = 0
            continue
        if not line.strip():
            if top not in TABLES:
                flush()
        else:
            buf.append(line)
    flush()
    emit()
    return chunks
