from procintel import db, paths


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
    assert set(db.SCHEMAS) == {paths.DB_PATH, paths.FEEDBACK_DB, paths.JOBS_DB}
