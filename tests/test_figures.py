from pathlib import Path

import duckdb

from procintel.core import paths
from procintel.ingestion import doc_figures, figure_text, figures

FIXTURE = Path(__file__).parent / "fixtures" / "icr_figure_page.pdf"   # page 55 of a World Bank completion report


def test_a_charts_image_and_caption_are_read_from_the_page(monkeypatch):
    monkeypatch.setattr(figures, "SKIP_PAGES", 0)         # the fixture is one page, not a report with a cover
    found = figures.figures(FIXTURE)
    assert len(found) == 1
    f = found[0]
    assert f.png.startswith(b"\x89PNG") and f.caption.startswith("Figure 1. Cumulative number of SIG targets")


def test_figures_are_stored_with_their_images_and_keep_descriptions_when_read_again(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    pdf = lambda p, c: figures.PdfFigure(p, (0, 0, 10, 10), c, b"\x89PNG fake")
    assert doc_figures.save(con, "d", "u", [pdf(3, "Figure 1. A"), pdf(4, None)]) == 2
    con.execute("UPDATE doc_figure SET description = 'A line chart.', described_by = 'm' WHERE fseq = 0")
    assert doc_figures.save(con, "d", "u", [pdf(3, "Figure 1. A"), pdf(5, "Figure 2. B")]) == 2
    rows = con.execute("SELECT page, caption, description FROM doc_figure ORDER BY fseq").fetchall()
    assert rows == [(3, "Figure 1. A", "A line chart."), (5, "Figure 2. B", None)]    # the same figure keeps its text
    got = doc_figures.for_chunks(con)["d"]
    assert [g["page"] for g in got] == [3, 5] and got[0]["description"] == "A line chart."
    from procintel.core import blob
    assert blob.store().get("figures/d/0.png") is not None
    con.close()


def test_describe_pending_fills_only_missing_descriptions(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    doc_figures.save(con, "d", "u", [figures.PdfFigure(3, (0, 0, 1, 1), "Figure 1. A", b"\x89PNG x")])
    con.close()
    monkeypatch.delenv("PROCINTEL_VISION_MODEL", raising=False)
    assert doc_figures.describe_pending(db)["described"] == 0                       # no vision model configured
    monkeypatch.setenv("PROCINTEL_VISION_MODEL", "m")
    monkeypatch.setenv("PROCINTEL_VISION_API_BASE", "http://x/v1")
    monkeypatch.setattr(figure_text, "describe", lambda png, caption=None: f"A chart. ({caption})")
    assert doc_figures.describe_pending(db) == {"described": 1, "failed": 0}
    con = duckdb.connect(str(db))
    assert con.execute("SELECT description, described_by FROM doc_figure").fetchone() == ("A chart. (Figure 1. A)", "m")
    con.close()
    assert doc_figures.describe_pending(db)["described"] == 0                       # nothing left to describe
