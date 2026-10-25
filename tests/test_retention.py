import os
import time
from datetime import date, datetime, timedelta

import duckdb

from procintel.core import paths
from procintel.jobs import retention


def _old(path, table, col, ages):
    con = duckdb.connect(str(path))
    con.execute(f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER, {col} TIMESTAMP)")
    con.executemany(f"INSERT INTO {table} VALUES (?, ?)", [(i, datetime.now() - timedelta(days=d)) for i, d in enumerate(ages)])
    con.close()


def test_dry_run_counts_then_apply_removes_only_what_is_old(tmp_path, monkeypatch):
    for name in ("PIPELINE_DB", "JOBS_DB", "FEEDBACK_DB", "DB_PATH"):
        monkeypatch.setattr(paths, name, tmp_path / f"{name}.duckdb")
    monkeypatch.setattr(paths, "HTTP_CACHE", tmp_path / "http")
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(retention, "PILOT_UNTIL", "")
    _old(paths.PIPELINE_DB, "event_log", "detected_at", [40, 31, 5])
    _old(paths.FEEDBACK_DB, "response_log", "created_at", [45, 2])
    _old(paths.FEEDBACK_DB, "feedback", "created_at", [45])
    con = duckdb.connect(str(paths.JOBS_DB))
    con.execute("CREATE TABLE jobs (id VARCHAR, status VARCHAR, created_at TIMESTAMP, finished_at TIMESTAMP)")
    old = datetime.now() - timedelta(days=40)
    con.executemany("INSERT INTO jobs VALUES (?, ?, ?, ?)", [("a", "done", old, old), ("b", "pending", old, None),
                                                             ("c", "done", datetime.now(), datetime.now())])
    con.close()
    paths.HTTP_CACHE.mkdir()
    for name, age in (("old.json", 40), ("new.json", 1)):
        f = paths.HTTP_CACHE / name
        f.write_text("{}")
        t = time.time() - age * 86400
        os.utime(f, (t, t))
    dry = retention.apply(dry=True)["removed"]
    assert dry == {"pipeline_history": 2, "finished_jobs": 1, "responses": 2, "http_cache": 1, "refresh_logs": 0,
                   "old_shadows": 0}
    assert (paths.HTTP_CACHE / "old.json").exists()                       # the dry run removed nothing
    assert retention.apply()["removed"] == dry
    assert sorted(p.name for p in paths.HTTP_CACHE.iterdir()) == ["new.json"]
    con = duckdb.connect(str(paths.JOBS_DB))
    assert sorted(r[0] for r in con.execute("SELECT id FROM jobs").fetchall()) == ["b", "c"]   # pending job kept
    con.close()
    assert retention.apply()["removed"]["pipeline_history"] == 0


def test_responses_are_kept_while_a_pilot_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "FEEDBACK_DB", tmp_path / "f.duckdb")
    _old(paths.FEEDBACK_DB, "response_log", "created_at", [90])
    monkeypatch.setattr(retention, "PILOT_UNTIL", (date.today() + timedelta(days=10)).isoformat())
    assert retention.responses(datetime.now() - timedelta(days=30), dry=True) == 0
    monkeypatch.setattr(retention, "PILOT_UNTIL", (date.today() - timedelta(days=1)).isoformat())
    assert retention.responses(datetime.now() - timedelta(days=30), dry=True) == 1
