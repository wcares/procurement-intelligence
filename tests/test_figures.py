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


def test_the_figure_route_serves_a_stored_image_and_refuses_bad_ids(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from procintel.api.routes import figures as route
    from procintel.core import blob
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    blob.store().put(doc_figures.image_key("d1", 0), b"\x89PNG fake")
    app = FastAPI()
    app.include_router(route.router)
    c = TestClient(app)
    ok = c.get("/figures/d1/0")
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/png" and ok.content == b"\x89PNG fake"
    assert c.get("/figures/d1/1").status_code == 404
    assert c.get("/figures/..%2Fetc/0").status_code == 404
    assert c.get("/figures/d1/5000").status_code == 404


def test_a_figure_citation_points_at_its_image(tmp_path, monkeypatch):
    from procintel.answering import answer
    from procintel.answering.retrieve import Hit
    from procintel.core import db
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "m.duckdb")
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    con = duckdb.connect(str(tmp_path / "m.duckdb"))
    doc_figures.save(con, "d1", "u", [figures.PdfFigure(9, (0, 0, 1, 1), "Figure 1. A", b"x"),
                                      figures.PdfFigure(12, (0, 0, 1, 1), None, b"y")])
    con.close()
    monkeypatch.setattr(db, "connect", lambda path=None, read_only=False: duckdb.connect(str(tmp_path / "m.duckdb")))
    base = dict(chunk_id="d1:3", doc_id="d1", title="t", doc_type="x", url="u", text="q", project_id="P", project_name="n",
                country_code="KE", score=1.0, via="bm25", tag=None, tag_confidence=None, problem=None)
    assert answer.citation(Hit(section="Figure 1. A", para="p.9", kind="figure", **base))["imageUrl"] == "/figures/d1/0"
    assert answer.citation(Hit(section="Figure, page 12", para="p.12", kind="figure", **base))["imageUrl"] == "/figures/d1/1"
    assert "imageUrl" not in answer.citation(Hit(section="S", para="3", kind="text", **base))
