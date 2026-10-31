from pathlib import Path

from procintel.ingestion import pdf_tables as T

FIXTURE = Path(__file__).parent / "fixtures" / "icr_financing_page.pdf"   # page 6 of a World Bank completion report


def test_clean_drops_empty_cells_template_markers_and_joins_wrapped_lines():
    raw = [["", "Indicator", None, "Result"],
           ["", "@#&OPS~Doctype~OPS Students", "", "158,871,976"],
           ["", "enhanced learning", "", "(number)"],
           ["", "", "", ""]]
    rows = T.clean(raw)
    assert rows == [["Indicator", "Result"], ["Students enhanced learning", "158,871,976 (number)"]]


def test_clean_keeps_a_new_entry_as_its_own_row():
    rows = T.clean([["Source", "Amount"], ["World Bank", "500"], ["Borrower", "2,846"]])
    assert len(rows) == 3


def test_clean_splits_rows_stacked_in_one_cell():
    rows = T.clean([["Source\nWorld Bank\nBorrower", "Amount\n500\n2,846"]])
    assert rows == [["Source", "Amount"], ["World Bank", "500"], ["Borrower", "2,846"]]


def test_pieces_repeat_the_header_and_respect_the_limit():
    t = T.PdfTable(3, "Table 2. Costs", [["Item", "US$"]] + [[f"Item number {i}", str(i * 1000)] for i in range(60)])
    parts = T.pieces(t, limit=400)
    assert len(parts) > 1
    assert parts[0].startswith("Table 2. Costs")
    assert all("| Item | US$ |" in p for p in parts)
    assert all(len(p) <= 400 for p in parts)
    assert sum(p.count("Item number") for p in parts) == 60


def test_tables_read_rows_and_columns_from_a_real_report_page():
    found = T.tables(FIXTURE)
    assert found and all(t.page == 1 for t in found)
    text = "\n".join(t.markdown for t in found)
    assert "| World Bank Financing |" in text and "500,000,000.00" in text
    assert "@#&" not in text


def test_doc_tables_reads_each_report_once_and_survives_a_bad_pdf(tmp_path, monkeypatch):
    import duckdb

    from procintel.ingestion import doc_tables
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE documents (doc_id VARCHAR, pdf_url VARCHAR)")
    con.execute("INSERT INTO documents VALUES ('a', 'http://x/a.pdf'), ('b', 'http://x/b.pdf'), ('c', NULL)")
    con.close()
    calls = []

    def fake_fetch(doc_id, url):
        calls.append(doc_id)
        if doc_id == "b":
            raise RuntimeError("no PDF")
        return f"pdfs/{doc_id}.pdf"

    import contextlib

    @contextlib.contextmanager
    def fake_copy(key, suffix=""):
        yield Path(key)

    monkeypatch.setattr(doc_tables, "fetch_pdf", fake_fetch)
    monkeypatch.setattr(doc_tables.pdf_tables, "tables", lambda path: [T.PdfTable(3, "Table 1. Costs", [["Item", "US$"], ["Roads", "500"]])])
    monkeypatch.setattr(doc_tables.blob, "local_copy", fake_copy)
    assert doc_tables.build(db) == {"read": 1, "tables": 1, "failed": 1, "left": 1}   # 'c' has no PDF address
    assert doc_tables.build(db)["read"] == 0 and calls == ["a", "b", "b"]              # 'a' is not fetched again
    con = duckdb.connect(str(db))
    got = doc_tables.for_chunks(con)
    con.close()
    assert list(got) == ["a"] and got["a"][0]["page"] == 3 and "| Roads | 500 |" in got["a"][0]["markdown"]
