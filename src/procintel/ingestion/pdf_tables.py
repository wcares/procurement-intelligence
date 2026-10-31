"""Tables read from a PDF's own layout (pdfplumber), as markdown, one passage per table.

The text exports the World Bank serves (`txturl`) flatten table columns into running words, so a row cannot be told
from its neighbour. The PDF still has the ruling lines and the character positions, which is enough to get rows and
cells back for digital reports (measured 2026-10-31 on three completion reports of 74-79 pages: 36-56 tables each,
3-4 s a report, no model). Tables with no ruling lines and scanned pages are left to a layout model later.

    tables(path) -> [PdfTable]            every table on every page, cleaned
    pieces(table, limit) -> [str]         the markdown cut into passages of at most `limit` characters, header repeated
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_CHARS = 1400            # same limit as the text passages
CAPTION_REACH = 45          # points above a table searched for its caption
MIN_FILLED = 0.2            # share of non-empty cells below which a "table" is page furniture
_TEMPLATE = re.compile(r"@#&\S*")   # the report template's own markers ("@#&OPS~Doctype~OPS^dynamics@...")
_CONTINUES = re.compile(r"[a-z0-9(\u2022]")   # what a wrapped line of a cell starts with (not a capital: that is a new entry)
_CAPTION = re.compile(r"^\s*(?:TABLE|Table|FIGURE|Figure)\s+[A-Z]?\d+(?:\.\d+)*\b.*", re.M)


@dataclass
class PdfTable:
    page: int                     # 1-based
    caption: str | None
    rows: list[list[str]]         # first row is the header

    @property
    def markdown(self) -> str:
        return _markdown(self.rows)


def _cell(c: str | None) -> str:
    return re.sub(r"\s+", " ", _TEMPLATE.sub("", (c or "").replace("|", "/"))).strip()


def _unstack(raw: list[list[str | None]]) -> list[list[str | None]]:
    """A raw row whose cells hold the same number of lines (several table rows drawn without ruling lines between
    them) becomes that many rows; a cell with another number of lines stays whole in the first of them."""
    out: list[list[str | None]] = []
    for r in raw:
        lines = [[l for l in (c or "").split("\n") if l.strip()] or [""] for c in r]
        counts = [len(l) for l in lines if len(l) > 1]
        n = max(set(counts), key=counts.count) if counts else 1
        if n < 2 or counts.count(n) < 2:
            out.append(r)
            continue
        for i in range(n):
            out.append([l[i] if len(l) == n else (" ".join(l) if i == 0 else "") for l in lines])
    return out


def clean(raw: list[list[str | None]]) -> list[list[str]]:
    """Cell text tidied, empty rows and columns dropped, and a row that only continues the cell text of the row above
    (a wrapped line: every filled cell starts in lower case, a digit, a bracket or a bullet and sits under text of the row above) joined to it."""
    rows = [[_cell(c) for c in r] for r in _unstack(raw)]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [j for j in range(width) if any(r[j] for r in rows)]
    rows = [[r[j] for j in keep] for r in rows]
    out: list[list[str]] = []
    for r in rows:
        if out and any(r) and all(not c or (_CONTINUES.match(c) and out[-1][j]) for j, c in enumerate(r)):
            for j, c in enumerate(r):
                if c:
                    out[-1][j] = f"{out[-1][j]} {c}"
        else:
            out.append(r)
    return out


def _markdown(rows: list[list[str]]) -> str:
    head = "| " + " | ".join(rows[0]) + " |"
    sep = "|" + "---|" * len(rows[0])
    return "\n".join([head, sep] + ["| " + " | ".join(r) + " |" for r in rows[1:]])


def _usable(rows: list[list[str]]) -> bool:
    if len(rows) < 2 or len(rows[0]) < 2:
        return False
    cells = [c for r in rows for c in r]
    return sum(bool(c) for c in cells) / len(cells) >= MIN_FILLED


def _caption(page, bbox) -> str | None:
    top = bbox[1]
    if top < 5:
        return None
    text = page.crop((0, max(0, top - CAPTION_REACH), page.width, top)).extract_text() or ""
    m = _CAPTION.findall(text)
    return _cell(m[-1]) if m else None


def tables(path: Path) -> list[PdfTable]:
    """Every table of the PDF, in page order. A page that cannot be read is skipped, not fatal."""
    import pdfplumber
    out: list[PdfTable] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                found = page.find_tables()
            except Exception:
                continue
            for t in found:
                rows = clean(t.extract())
                if _usable(rows):
                    out.append(PdfTable(i + 1, _caption(page, t.bbox), rows))
    return out


def pieces(t: PdfTable, limit: int = MAX_CHARS) -> list[str]:
    """The table as markdown passages of at most `limit` characters: caption first, header row repeated in every
    piece, rows never cut (a single row longer than the limit is its own piece)."""
    lead = f"{t.caption}\n\n" if t.caption else ""
    head = _markdown(t.rows[:1]).split("\n")
    parts: list[list[str]] = [[]]
    size = len(lead) + sum(len(l) + 1 for l in head)
    for r in t.rows[1:]:
        line = "| " + " | ".join(r) + " |"
        if parts[-1] and size + len(line) + 1 > limit:
            parts.append([])
            size = sum(len(l) + 1 for l in head)
        parts[-1].append(line)
        size += len(line) + 1
    return [(lead if i == 0 else "") + "\n".join(head + p) for i, p in enumerate(parts)]
