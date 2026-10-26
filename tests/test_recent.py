from datetime import datetime

from procintel.insights import recent
from procintel.pipeline import store


def test_recent_counts_source_changes_in_planner_words(tmp_path):
    db = tmp_path / "p.duckdb"
    con = store.connect(db)
    rows = [("Notice.added", "N1", "2026-10-20 10:00"), ("Notice.added", "N2", "2026-10-21 10:00"),
            ("Project.added", "P1", "2026-10-19 09:00"), ("Data.updated", "all", "2026-10-21 11:00"),  # bookkeeping
            ("Notice.changed", "N0", "2026-09-01 10:00")]                                              # too old
    for i, (t, k, at) in enumerate(rows):
        con.execute("INSERT INTO event_log VALUES (?, 'b', ?, ?, '[]', NULL, NULL, ?)", [str(i), t, k, at])
    con.close()
    r = recent.recent(14, db, now=datetime(2026, 10, 26))
    assert [(i["type"], i["count"], i["examples"]) for i in r["items"]] == [
        ("Notice.added", 2, ["N2", "N1"]), ("Project.added", 1, ["P1"])]              # newest kind first
    assert r["items"][0]["label"] == "new procurement notices" and r["total"] == 3
