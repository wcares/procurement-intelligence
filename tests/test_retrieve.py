import duckdb
import pytest

from procintel.retrieve import Retriever

CHUNKS = [
    ("d1:0", "d1", 0, "Lessons", "12", "text", "Civil works contracts were terminated because the contractor abandoned the road site."),
    ("d1:1", "d1", 1, "Lessons", "13", "table", "Component Appraisal Actual civil works contracts terminated 12.4 10.1"),
    ("d2:0", "d2", 0, "Key Factors", "30", "text", "Consultant selection was delayed and the terms of reference were revised twice."),
    ("d3:0", "d3", 0, "Key Factors", "8", "text", "The goods contract for laboratory equipment was cancelled after rebidding failed."),
]


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE chunk (chunk_id VARCHAR, doc_id VARCHAR, seq INT, section VARCHAR, para VARCHAR, kind VARCHAR, text VARCHAR)")
    con.executemany("INSERT INTO chunk VALUES (?,?,?,?,?,?,?)", CHUNKS)
    con.execute("CREATE TABLE document_m AS SELECT * FROM (VALUES ('d1','ICR','Road ICR','u1'),('d2','ICR','Health ICR','u2'),('d3','ICR','Lab ICR','u3')) t(doc_id, doc_type, title, pdf_url)")
    # d1 covers two projects in different countries
    con.execute("CREATE TABLE document_project AS SELECT * FROM (VALUES ('d1','P1'),('d1','P9'),('d2','P2'),('d3','P3')) t(doc_id, project_id)")
    con.execute("CREATE TABLE project AS SELECT * FROM (VALUES ('P1','Roads','KE'),('P9','Roads II','TZ'),('P2','Health','KE'),('P3','Labs','IN')) t(project_id, name, country_code)")
    con.close()
    return Retriever(db)


def test_tables_are_excluded_by_default(retriever):
    assert "d1:1" not in [h.chunk_id for h in retriever.search("civil works contracts terminated")]


def test_country_filter_and_cited_project_follows_it(retriever):
    hits = retriever.search("contract terminated cancelled", country="TZ")
    assert [h.chunk_id for h in hits] == ["d1:0"]
    assert (hits[0].project_id, hits[0].country_code) == ("P9", "TZ")


def test_procurement_group_filter(retriever):
    assert [h.chunk_id for h in retriever.search("contract cancelled terminated", proc_group="GO")] == ["d3:0"]


def test_no_term_overlap_returns_nothing(retriever):
    assert retriever.search("photosynthesis") == []


@pytest.fixture
def hybrid(retriever, monkeypatch):
    """The same 4-chunk retriever with fake unit vectors: the query vector is closest to d2:0 (no shared terms)."""
    import numpy as np
    from procintel import embed
    vecs = np.array([[1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32)  # d1:0, d1:1, d2:0, d3:0
    monkeypatch.setattr(retriever, "vectors", vecs)
    monkeypatch.setattr(embed, "embed", lambda texts: np.array([[0.1, 0.99, 0.0]], dtype=np.float32))
    return retriever


def test_vector_search_finds_a_passage_with_no_shared_terms(hybrid):
    hits = hybrid.search("slow hiring of advisers")
    assert hits[0].chunk_id == "d2:0" and hits[0].via == "vector"


def test_filters_apply_to_vector_results(hybrid):
    assert "d2:0" not in [h.chunk_id for h in hybrid.search("slow hiring of advisers", country="IN")]


def test_embedding_failure_falls_back_to_bm25(hybrid, monkeypatch):
    from procintel import embed

    def down(texts):
        raise ConnectionError("embedding server not running")
    monkeypatch.setattr(embed, "embed", down)
    hits = hybrid.search("contract cancelled terminated")
    assert hits and all(h.via == "bm25" for h in hits)


def test_precedents_skip_passages_tagged_as_no_problem(retriever, monkeypatch):
    from procintel import assess
    from procintel.tag import NONE
    tagged = {"d1:0": (NONE, 0.9), "d3:0": ("re-tendering or contract termination", 0.8)}
    for r in retriever.records:
        r["tag"], r["tag_confidence"] = tagged.get(r["chunk_id"], (None, 0.0))
    try:
        precs, _, _ = assess.precedents(retriever, "KE", "CW", "contract cancelled terminated", "")
        ids = [p["citation"]["id"] for p in precs]
        assert "d1:0" not in ids  # confidently "no problem": not a precedent
    finally:
        for r in retriever.records:
            r["tag"], r["tag_confidence"] = None, 0.0
