"""Figures (charts, maps, photos, diagrams) found in a PDF: the page region as a PNG and the caption printed next to it.

Embedded images larger than MIN_WIDTH x MIN_HEIGHT points are taken as figures; the cover photo (page 1) and exact
repeats of the same region on a page are dropped. The caption is the "Figure 3. ..." / "Photo ..." / "Map ..." line
printed just below the image (World Bank reports) or just above it. Describing the image is a separate step
(procintel.ingestion.figure_text), so a report without a vision model still gets its figures and captions.

    figures(path) -> [PdfFigure]
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

MIN_WIDTH = 120          # points; smaller images are logos and icons
MIN_HEIGHT = 80
SKIP_PAGES = 1           # the cover page's photo
CAPTION_REACH = 60       # points searched below and above the image for its caption
RESOLUTION = 110         # dpi of the saved crop: enough to read chart labels, small enough to store and send
_CAPTION = re.compile(r"^\s*((?:FIGURE|Figure|Chart|CHART|Photo|PHOTO|Map|MAP|Box|BOX)\s+[A-Z]?\d+(?:\.\d+)*\b.*)", re.M)


@dataclass
class PdfFigure:
    page: int                 # 1-based
    bbox: tuple[float, float, float, float]
    caption: str | None
    png: bytes


def _caption(page, bbox) -> str | None:
    x0, top, x1, bottom = bbox
    for lo, hi in ((bottom, min(page.height, bottom + CAPTION_REACH)), (max(0, top - CAPTION_REACH), top)):
        if hi - lo < 4:
            continue
        text = page.crop((0, lo, page.width, hi)).extract_text() or ""
        m = _CAPTION.search(text)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()[:300]
    return None


def figures(path: Path) -> list[PdfFigure]:
    """Every figure of the PDF in page order. A page that cannot be read or rendered is skipped, not fatal."""
    import pdfplumber
    out: list[PdfFigure] = []
    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            if i < SKIP_PAGES:
                continue
            seen: set[tuple[int, ...]] = set()
            try:
                images = list(page.images)
            except Exception:
                continue
            for im in images:
                w, h = im["x1"] - im["x0"], im["bottom"] - im["top"]
                bbox = (max(0, im["x0"]), max(0, im["top"]), min(page.width, im["x1"]), min(page.height, im["bottom"]))
                key = tuple(round(v / 4) for v in bbox)
                if w < MIN_WIDTH or h < MIN_HEIGHT or key in seen:
                    continue
                seen.add(key)
                try:
                    buf = io.BytesIO()
                    page.crop(bbox).to_image(resolution=RESOLUTION).original.save(buf, format="PNG")
                except Exception:
                    continue
                out.append(PdfFigure(i + 1, bbox, _caption(page, bbox), buf.getvalue()))
    return out
