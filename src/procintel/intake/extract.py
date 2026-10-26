"""Text by format: one string per page (PDF) or one for the whole file. Adding a format = one reader in READERS.

A PDF without a text layer (a scan) gives no text; reading scans needs OCR, which is not installed, so such a file is
reported for review rather than guessed at."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

MAX_BYTES = 50 * 1024 * 1024


def _pdf(path: Path) -> list[str]:
    from pypdf import PdfReader
    return [p.extract_text() or "" for p in PdfReader(str(path)).pages]


def _docx(path: Path) -> list[str]:
    import docx
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        parts += [" | ".join(c.text for c in row.cells) for row in t.rows]
    return ["\n".join(parts)]


def _text(path: Path) -> list[str]:
    return [path.read_text(errors="replace")]


def _html(path: Path) -> list[str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(path.read_text(errors="replace"), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return [soup.get_text("\n")]


READERS: dict[str, Callable[[Path], list[str]]] = {
    "pdf": _pdf, "docx": _docx, "txt": _text, "md": _text, "html": _html, "htm": _html}


def format_of(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in READERS else None


def pages(path: Path, fmt: str) -> list[str]:
    return READERS[fmt](path)
