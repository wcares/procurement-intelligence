from datetime import timedelta
from pathlib import Path

from procintel.core import paths
from procintel.ingestion import isr_chunk, supervision
from procintel.jobs import store as jobs_store
from procintel.pipeline import detect, entities, store

ISR = (Path(__file__).parent / "fixtures" / "isr_P105680.txt").read_text()   # first 3 pages of a real ISR (P105680)


def test_an_isr_keeps_ratings_status_and_risks_with_section_anchors():
    cs = isr_chunk.chunk_isr(ISR)
    assert [(c.section.split(":")[0], c.kind) for c in cs] == [
        ("Overall Ratings", "table"), ("Key Issues & Status", "text"), ("Key Issues & Status", "text"),
        ("Systematic Operations Risk-Rating Tool", "table")]
    assert cs[1].section == "Key Issues & Status: Implementation Status And Key Decisions" and cs[1].para == "4.1·1"
    assert cs[2].para == "4.1·2-5"                               # short paragraphs joined, the range kept as the anchor
    text = " ".join(c.text for c in cs)
    assert "Fiduciary" in cs[3].text and "Page 2 of 9" not in text and "Development Objective" not in text
    assert all("Implementation Status &" not in c.text for c in cs)     # running header removed


def test_restructuring_papers_are_told_from_additional_financing():
    class Client:
        def documents(self, rows, docty_exact, projectid):
            if docty_exact == supervision.ISR_TYPE:
                return 2, [{"id": "i2", "docdt": "2026-04-07", "txturl": "t", "display_title": "ISR"},
                           {"id": "i1", "docdt": "2025-11-11", "txturl": "t", "display_title": "ISR"}]
            return 3, [{"id": "a", "txturl": "t", "display_title": "Argentina - X Project : Second Additional Financing"},
                       {"id": "r", "txturl": "t", "display_title": "Disclosable Restructuring Paper - X Project - P1"},
                       {"id": "r0", "txturl": None, "display_title": "Restructuring Paper (no text)"}]
    rows = supervision.for_project(Client(), "P1")
    assert [(r["doc_id"], r["doc_type"]) for r in rows] == [("i2", supervision.ISR_TYPE), ("r", supervision.RESTRUCTURING_TYPE)]


def test_a_type_new_to_the_database_reads_its_source_instead_of_seeding_forever(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    monkeypatch.setattr(jobs_store, "DB_PATH", tmp_path / "jobs.duckdb")
    source = {"i2": {"doc_id": "i2", "doc_type": "ISR", "doc_date": None, "title": "t", "txt_url": "u"}}
    fake = entities.EntityType("SupervisionDoc", timedelta(days=1), ["doc_type", "title"], lambda ctx: (dict(source), False),
                               lambda: {})                        # nothing in the database yet
    monkeypatch.setattr(entities, "ENTITY_TYPES", {"SupervisionDoc": fake})
    gen = detect.detect_steps({"force": True}, None, {})
    try:
        while True:
            next(gen)
    except StopIteration as s:
        out = s.value
    assert out["events"] == {"SupervisionDoc": 1} and out["job"]  # read at once: the document is new
    assert [e["type"] for e in store.batch_events(out["batch"])] == ["SupervisionDoc.added"]


def test_windows_line_ends_cut_like_unix_ones():
    from procintel.ingestion import chunk
    text = ("I. PROJECT STATUS AND RATIONALE FOR RESTRUCTURING\n\n1.      The project closing date is extended by six months "
            "because the main civil works contract was delayed by a re-tender after the first bids exceeded the cost estimate.\n"
            "2.      Procurement is rated Moderately Satisfactory; the procurement plan was updated in STEP.\n")
    unix = chunk.chunk_document(text)
    assert len(unix) == 2 and [c.para for c in unix] == ["1", "2"]
    assert [(c.para, c.text) for c in chunk.chunk_document(text.replace("\n", "\r\n"))] == [(c.para, c.text) for c in unix]
