"""Section-aware chunking of ICR plain text (the WDS `txturl` output, which is pdf-to-text).

Layout facts this relies on (observed in the ingested ICRs):
  - pages are separated by form feeds and end with an "Official Use Only ... Page N" footer;
  - footnotes sit at the bottom of a page: a line holding only the footnote number, then its text;
  - body paragraphs are numbered ("23.      Given the scope ..."), which gives a stable citation anchor;
  - section headings are short all-caps lines; the table of contents uses dot leaders.

    python -m procintel.chunk          # builds the `chunk` table from `documents`
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "procintel.duckdb"
MAX_CHARS = 1400

_FOOTER_LINE = re.compile(r"^\s*(?:Page \d{1,3}(?: of \d{1,3})?)?\s*$")
_FOOTER_WORDS = re.compile(r"\s*(?:Official Use Only|Strictly Confidential)\s*")
# pdf-to-text sometimes glues the footer's page number onto the next line: "Page 3 enhanced resilience ..."
_PAGE_PREFIX = re.compile(r"^\s*Page \d{1,3}(?: of \d{1,3})?\s+(?=\S)")
_RUNNING_HEADER = re.compile(r"^\s*The World Bank\s*$|ICR DOCUMENT\s*$|\(P\d{6}\)\s*$")
_HEADER_END = re.compile(r"\(P\d{6}\)|ICR DOCUMENT", re.I)
_TEMPLATE_MARK = re.compile(r"@#&OPS~")
HEADER_WINDOW = 5  # the running header (bank name, project title wrapped over 1-3 lines) fits in this many lines
_FOOTNOTE_MARK = re.compile(r"^\s*\d{1,3}\s*$")
_PARA_START = re.compile(r"^\s{0,6}(\d{1,3})\.\s+(\S.*)$")
_HEADING = re.compile(r"^\s*(?:[IVX]+\.|ANNEX\s+\d+\.?|[A-H]\.)?\s*[A-Z][A-Z ,/&()'’:-]{6,90}$")
_TOC = re.compile(r"\.{5,}")
_MOJIBAKE = re.compile(r"�[^\w\s]?�?|�")
_COLUMN_GAP = re.compile(r"\S\s{3,}\S")

# Sections that hold staff lists or cost tables rather than findings.
SKIP_SECTIONS = re.compile(r"task team|bank lending|staff time|supervision cost|data sheet|front matter|abbreviations|acronyms|table of contents", re.I)


@dataclass
class Chunk:
    section: str
    para: str | None  # numbered paragraph anchor, e.g. "23"
    kind: str  # "text" | "table"
    text: str


def _drop_running_header(lines: list[str]) -> list[str]:
    """Remove each "The World Bank / <project title, possibly wrapped> (P######) ICR Document" block.

    Matched as a block rather than per line, because a wrapped title's first line matches nothing on its own.
    It usually sits at the top of a page, but some extractions have no form feeds, so it is found anywhere:
    a line that is exactly "The World Bank", through the last line carrying the project id or "ICR Document"
    in the unbroken run of lines after it. The run ends at a blank line or a numbered paragraph, so a project
    id in the body text that follows the header is never taken as the header's end."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == "The World Bank":
            run = []
            for j in range(i + 1, min(len(lines), i + HEADER_WINDOW)):
                if not lines[j].strip() or _PARA_START.match(lines[j]):
                    break
                run.append(j)
            ends = [j for j in run if _HEADER_END.search(lines[j])]
            i = (ends[-1] if ends else i) + 1
            continue
        out.append(lines[i])
        i += 1
    return out


def strip_page_furniture(page: str) -> list[str]:
    """Lines of one page without running header, footer and the footnote block above the footer.

    Footer words ("Official Use Only", "Strictly Confidential") appear both in the page footer and as
    standalone lines elsewhere (cover page, top of page), so they are removed line by line; the header block
    and the footnote cut are positional.
    """
    lines = []
    for l in _drop_running_header(page.split("\n")):
        if _TEMPLATE_MARK.search(l):
            continue
        had_footer_words = bool(_FOOTER_WORDS.search(l))
        l = _FOOTER_WORDS.sub(" ", l)
        # a footer-only line is dropped, not left blank: a blank line would end an unnumbered block mid-passage
        if _FOOTER_LINE.match(l) and (l.strip() or had_footer_words):
            continue
        l = _PAGE_PREFIX.sub("", l)
        if _RUNNING_HEADER.search(l):
            continue
        lines.append(l)
    while lines and not lines[-1].strip():
        lines.pop()
    # footnote block: a bare number line in the lower part of the page, preceded by a blank line
    for i in range(int(len(lines) * 0.4), len(lines)):
        if _FOOTNOTE_MARK.match(lines[i]) and i > 0 and not lines[i - 1].strip():
            return lines[:i]
    return lines


def _is_table(lines: list[str]) -> bool:
    content = [l for l in lines if l.strip()]
    if not content:
        return False
    tabular = sum(1 for l in content if len(_COLUMN_GAP.findall(l.strip())) >= 2)
    return tabular / len(content) > 0.5


def _clean(s: str) -> str:
    s = _MOJIBAKE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _split_words(text: str, limit: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + len(w) + 1 > limit:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


def _split_long(text: str, limit: int = MAX_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    pieces = []
    for sent in re.split(r"(?<=[.;])\s+(?=[A-Z0-9])", text):
        # a table row run or run-on text has no sentence end to cut at; fall back to word boundaries
        pieces.extend(_split_words(sent, limit) if len(sent) > limit else [sent])
    for sent in pieces:
        if cur and len(cur) + len(sent) + 1 > limit:
            out.append(cur)
            cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        out.append(cur)
    return out


def chunk_document(text: str) -> list[Chunk]:
    lines: list[str] = []
    for page in text.split("\x0c"):
        lines.extend(strip_page_furniture(page))

    chunks: list[Chunk] = []
    section, para = "Front Matter", None
    last_para: str | None = None  # survives section changes, which reset `para`
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        kind = "table" if _is_table(buf) else "text"
        body = _clean(" ".join(buf))
        buf.clear()
        if len(body) < 80:
            return
        for piece in _split_long(body):
            chunks.append(Chunk(section, para, kind, piece))

    for line in lines:
        if _TOC.search(line):
            continue
        stripped = line.strip()
        if _HEADING.match(line) and not stripped.endswith(".") and len(stripped) < 95:
            flush()
            section, para = re.sub(r"\s+", " ", stripped).title(), None
            continue
        m = _PARA_START.match(line)
        # paragraph numbers run in sequence through the body; requiring the next number keeps
        # numbered lists inside a paragraph ("1. ...", "2. ...") from being taken as new paragraphs
        # a gap of up to 3 tolerates a paragraph whose number the text extraction mangled
        if m and (last_para is None or 0 < int(m.group(1)) - int(last_para) <= 3):
            flush()
            para = last_para = m.group(1)
            buf.append(m.group(2))
            continue
        if not stripped:
            # blank lines separate un-numbered blocks (tables, bullet groups); numbered paragraphs
            # often contain page breaks, so only flush when the buffer is not a numbered paragraph
            if para is None:
                flush()
            continue
        buf.append(line)
    flush()
    return [c for c in chunks if not SKIP_SECTIONS.search(c.section)]


def build(db_path: Path = DB_PATH) -> None:
    con = duckdb.connect(str(db_path))
    rows = []
    for doc_id, text in con.execute("SELECT doc_id, text FROM documents").fetchall():
        for i, c in enumerate(chunk_document(text)):
            rows.append({"chunk_id": f"{doc_id}:{i}", "doc_id": doc_id, "seq": i, "section": c.section,
                         "para": c.para, "kind": c.kind, "text": c.text, "n_chars": len(c.text)})
    df = pd.DataFrame(rows)
    con.execute("CREATE OR REPLACE TABLE chunk AS SELECT * FROM df")
    print(f"chunk: {len(df)} rows from {df.doc_id.nunique()} documents")
    con.close()


if __name__ == "__main__":
    build()
