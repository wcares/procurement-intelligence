from datetime import timedelta

import pandas as pd

from procintel.core import paths
from procintel.jobs import store as jobs_store
from procintel.pipeline import actions, detect, entities, rules, store


def test_norm_makes_source_and_database_values_equal():
    assert store.norm(pd.Timestamp("2026-09-30", tz="UTC")) == store.norm(pd.Timestamp("2026-09-29 20:00", tz="America/New_York"))
    assert store.norm(pd.Timestamp("2020-12-15")) == store.norm("2020-12-15") == "2020-12-15"   # a DATE column
    assert store.norm(0.0) == store.norm(0) == 0 and store.norm(float("nan")) is None
    assert store.norm('[{"b": 1, "a": 2}]') == store.norm([{"a": 2, "b": 1}])


def test_diff_reports_added_changed_and_removals_only_for_a_complete_read():
    known = {"a": (store.fingerprint({"v": 1}), {"v": 1}), "b": (store.fingerprint({"v": 2}), {"v": 2})}
    rows = {"a": {"v": 1}, "c": {"v": 3}}
    assert {e["type"] for e in store.diff("X", ["v"], rows, known, complete=False)} == {"X.added"}
    ev = store.diff("X", ["v"], {"a": {"v": 9}, "b": {"v": 2}}, known, complete=True)
    assert [(e["type"], e["key"], e["changed"]) for e in ev] == [("X.changed", "a", ["v"])]
    assert [e["type"] for e in store.diff("X", ["v"], {"a": {"v": 1}}, known, complete=True)] == ["X.removed"]


def test_rules_plan_coalesces_and_follows_the_registry_order():
    events = [{"type": "Notice.added", "key": "n1"}, {"type": "Notice.changed", "key": "n2", "changed": ["award_date"]},
              {"type": "Project.changed", "key": "p1", "changed": ["name"]}]          # name is not a watched rule field
    plan, fired = rules.plan(events, rules.DEFAULT_RULES, actions.ORDER)
    assert plan == [("apply_notices", ["n1", "n2"]), ("rebuild_tables", ["n1", "n2"]), ("rebuild_firms", ["n1", "n2"])]
    assert fired == {"notices-update-packages": 2}


def test_a_new_report_is_ingested_chunked_then_indexed_and_checked():
    plan, _ = rules.plan([{"type": "Document.added", "key": "d9"}], rules.DEFAULT_RULES, actions.ORDER)
    assert [a for a, _ in plan] == ["ingest_documents", "rebuild_tables", "rebuild_firms", "chunk_documents"]
    derived = [{"type": "Passages.changed", "key": "all"}, {"type": "Data.updated", "key": "all"}]
    plan, _ = rules.plan(derived, rules.DEFAULT_RULES, actions.ORDER)
    assert [a for a, _ in plan] == ["index_passages", "document_checks", "reload_backend"]
    assert actions.ORDER.index("chunk_documents") < actions.ORDER.index("index_passages")


def test_detection_replay_records_events_queues_one_batch_and_the_batch_follows_derived_events(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    monkeypatch.setattr(jobs_store, "DB_PATH", tmp_path / "jobs.duckdb")
    source = {"n1": {"id": "n1", "award_date": None}, "n2": {"id": "n2", "award_date": None}}
    fake = entities.EntityType("Notice", timedelta(hours=1), ["award_date"],
                               lambda ctx: ({k: dict(v) for k, v in source.items()}, False), lambda: dict(source))
    monkeypatch.setattr(entities, "ENTITY_TYPES", {"Notice": fake})
    ran = []

    def recorder(name, emits):
        return actions.Action(name, name, lambda keys, evs, ctx: ran.append((name, keys, sorted(evs))) or emits)
    monkeypatch.setattr(actions, "ACTIONS", {
        "apply_notices": recorder("apply_notices", [{"type": "Data.updated", "key": "all"}]),
        "rebuild_tables": recorder("rebuild_tables", [{"type": "Package.award_changed", "key": "all"}]),
        "rebuild_firms": recorder("rebuild_firms", []),
        "drift_check": recorder("drift_check", []),
        "reload_backend": recorder("reload_backend", [])})
    monkeypatch.setattr(actions, "ORDER", list(actions.ACTIONS))

    out = _run(detect.detect_steps({"force": True}, None, {}))                 # first run: seeded, no events
    assert out["events"] == {"Notice": 0} and out["job"] is None and len(store.states("Notice")) == 2

    source["n2"]["award_date"] = "2026-10-01"                                   # one award recorded, one notice new
    source["n3"] = {"id": "n3", "award_date": None}
    out = _run(detect.detect_steps({"force": True}, None, {}))
    assert out["events"] == {"Notice": 2} and out["job"]
    logged = store.batch_events(out["batch"])
    assert sorted((e["type"], e["key"]) for e in logged) == [("Notice.added", "n3"), ("Notice.changed", "n2")]
    assert store.overview()["firings"][0]["rule"] == "notices-update-packages"

    job = jobs_store.next_pending()
    assert job["kind"] == "pipeline_batch"
    result = _run(detect.batch_steps(job["params"], None, {}))
    assert [r[0] for r in ran] == ["apply_notices", "rebuild_tables", "rebuild_firms", "drift_check", "reload_backend"]
    assert ran[0][1] == ["n2", "n3"] and ran[0][2] == ["n2", "n3"]              # the action got exactly its rows
    assert result["derived"] == ["Data.updated", "Package.award_changed"]
    assert {e["type"] for e in store.batch_events(out["batch"])} >= {"Data.updated", "Package.award_changed"}

    out = _run(detect.detect_steps({"force": True}, None, {}))                  # nothing changed since
    assert out["events"] == {"Notice": 0} and out["job"] is None


def _run(gen):
    try:
        while True:
            next(gen)
    except StopIteration as s:
        return s.value


def test_kept_report_dates_are_read_back_in_utc():
    """ingest.run(keep_existing=True) re-reads stored dates; formatting a zoned time in the session's zone and calling
    it UTC moved every report 4 hours per refresh (New York session)."""
    import duckdb
    con = duckdb.connect()
    con.execute("SET TimeZone = 'America/New_York'")
    con.execute("CREATE TABLE d AS SELECT TIMESTAMPTZ '2026-06-26 04:00:00+00' AS doc_date")
    got = con.execute("SELECT strftime(timezone('UTC', doc_date), '%Y-%m-%dT%H:%M:%SZ') FROM d").fetchone()[0]
    assert got == "2026-06-26T04:00:00Z"
    assert con.execute("SELECT strftime(doc_date, '%Y-%m-%dT%H:%M:%SZ') FROM d").fetchone()[0] != got   # the old form
