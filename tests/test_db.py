from procintel.core import db, paths


def test_default_backend_is_duckdb_files(monkeypatch, tmp_path):
    monkeypatch.delenv("PROCINTEL_DB_URL", raising=False)
    assert db.backend() == "duckdb"
    con = db.connect(tmp_path / "x.duckdb")
    assert con.execute("SELECT 42").fetchone() == (42,)
    con.close()


def test_postgres_url_selects_postgres_only_for_the_known_databases(monkeypatch, tmp_path):
    monkeypatch.setenv("PROCINTEL_DB_URL", "postgresql://u:p@localhost:1/x")
    assert db.backend() == "postgres"
    con = db.connect(tmp_path / "scratch.duckdb")   # not one of the three databases: stays a DuckDB file
    assert con.execute("SELECT 1").fetchone() == (1,)
    con.close()
    assert sorted(db.SCHEMAS.values()) == ["auth", "feedback", "jobs", "pipeline", "public"]


def test_suppliers_read_from_json_text_and_from_older_struct_lists():
    import duckdb
    from procintel.ingestion.tables import SUPPLIERS
    con = duckdb.connect()
    q = f"SELECT s.firm_id, s.name FROM (SELECT UNNEST(from_json(suppliers::JSON, '{SUPPLIERS}')) AS s FROM t) ORDER BY 1"
    con.execute("""CREATE TABLE t AS SELECT '[{"name": "ACME", "firm_id": 7}]' AS suppliers""")         # JSON text
    assert con.execute(q).fetchall() == [(7, "ACME")]
    con.execute("CREATE OR REPLACE TABLE t AS SELECT [{'name': 'ACME', 'firm_id': 7}] AS suppliers")      # older form
    assert con.execute(q).fetchall() == [(7, "ACME")]
