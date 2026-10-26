"""Reading scanned pages (procintel.intake.extract uses it for PDF pages without a text layer).

PROCINTEL_OCR picks the engine: "vision" (Apple Vision through ocrmac, macOS only), "rapidocr" (ONNX models, any
platform: the choice for Linux containers), "off", or "auto" (the default: vision where it is available, else
rapidocr, else off). Adding an engine = one function in ENGINES. Measured 2026-10-26 on 8 rendered pages of real
uploads against their text layer: vision word F1 0.948 at 0.41 s a page, rapidocr 0.884 at 1.32 s.
"""
from __future__ import annotations

import os
import sys
from typing import Callable

DPI = 200
MAX_PAGES = 80      # pages OCR'd per file at most (about half a minute with vision)


def _vision(image) -> str:
    from ocrmac import ocrmac
    return "\n".join(t for t, _conf, _box in ocrmac.OCR(image, recognition_level="accurate").recognize())


_rapid = None


def _rapidocr(image) -> str:
    global _rapid
    if _rapid is None:
        from rapidocr import RapidOCR
        _rapid = RapidOCR()
    return "\n".join(_rapid(image).txts or [])


ENGINES: dict[str, Callable] = {"vision": _vision, "rapidocr": _rapidocr}


def _importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def engine() -> str | None:
    """The engine in use, or None when OCR is off or nothing is installed."""
    want = os.environ.get("PROCINTEL_OCR", "auto").lower()
    if want == "off":
        return None
    if want in ENGINES:
        return want
    if sys.platform == "darwin" and _importable("ocrmac"):
        return "vision"
    return "rapidocr" if _importable("rapidocr") else None


def read_pdf_pages(path, numbers: list[int]) -> dict[int, str]:
    """OCR text of the given PDF pages (0-based), up to MAX_PAGES of them; empty when OCR is unavailable."""
    name = engine()
    if not name or not numbers:
        return {}
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(path))
    try:
        return {i: ENGINES[name](doc[i].render(scale=DPI / 72).to_pil()) for i in numbers[:MAX_PAGES]}
    finally:
        doc.close()
