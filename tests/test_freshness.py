from datetime import datetime

from procintel.core import paths
from procintel.pipeline import freshness, store


def test_each_source_reports_its_last_good_read_and_whether_it_is_late(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "p.duckdb")
    con = store.connect()
    con.execute("CREATE TABLE IF NOT EXISTS detection (batch_id VARCHAR, entity_type VARCHAR, ran_at TIMESTAMP, items INTEGER, "
                "events INTEGER, note VARCHAR, error VARCHAR)")
    con.executemany("INSERT INTO detection VALUES ('b', ?, ?, 1, 0, NULL, ?)", [
        ("Notice", datetime(2026, 10, 31, 10), None), ("Notice", datetime(2026, 10, 31, 11), "timeout"),
        ("Project", datetime(2026, 10, 30, 0), None)])
    con.close()
    got = {s["entity"]: s for s in freshness.sources(now=datetime(2026, 10, 31, 12))}
    assert got["Notice"]["hoursAgo"] == 2.0 and not got["Notice"]["late"]            # the failed read does not count
    assert got["Project"]["hoursAgo"] == 36.0 and got["Project"]["late"]             # read hourly, last good 36 h ago
    assert got["Indicator"]["lastRead"] is None and got["Indicator"]["late"]
    assert got["Notice"]["label"] == "procurement notices"
