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
