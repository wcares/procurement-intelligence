import pytest
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
    assert plan == [("apply_notices", ["n1", "n2"]), ("rebuild_tables", ["n1", "n2"]), ("rebuild_firms", ["n1", "n2"]),
                    ("watch_alerts", ["n1", "n2"])]
    assert fired == {"notices-update-packages": 2, "watch-alerts": 2}


def test_a_new_report_is_ingested_chunked_then_indexed_and_checked():
    plan, _ = rules.plan([{"type": "Document.added", "key": "d9"}], rules.DEFAULT_RULES, actions.ORDER)
    assert [a for a, _ in plan] == ["ingest_documents", "rebuild_tables", "rebuild_firms", "chunk_documents",
                                    "watch_alerts"]
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
        "watch_alerts": recorder("watch_alerts", []),
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
    assert {f["rule"] for f in store.overview()["firings"]} == {"notices-update-packages", "watch-alerts"}

    job = jobs_store.next_pending()
    assert job["kind"] == "pipeline_batch"
    result = _run(detect.batch_steps(job["params"], None, {}))
    assert [r[0] for r in ran] == ["apply_notices", "rebuild_tables", "rebuild_firms", "drift_check", "watch_alerts",
                                   "reload_backend"]
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


def test_rule_validation_refuses_unknown_names_bad_fields_and_cycles():
    E, A = entities.ENTITY_TYPES, actions.ACTIONS
    assert rules.validate(list(rules.DEFAULT_RULES), E, A) == {}                       # the defaults are valid
    bad = [rules.Rule("x", ("Notice.exploded",), ("apply_notices",)),
           rules.Rule("y", ("Notice.added",), ("launch_rockets",)),
           rules.Rule("z", ("Project.changed",), ("apply_projects",), fields=("colour",))]
    errors = rules.validate(bad, E, A)
    assert set(errors) == {"x", "y", "z"} and "unknown events" in errors["x"] and "colour" in errors["z"]
    loop = [rules.Rule("a", ("Passages.changed",), ("chunk_documents",))]           # chunking emits Passages.changed
    assert "cycle" in rules.validate(loop, E, A)["(set)"]


def test_saved_rules_replace_the_defaults_until_reset_and_dry_run_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PIPELINE_RULES", tmp_path / "rules.json")
    only = [rules.Rule("awards-only", ("Notice.added",), ("apply_notices",))]
    assert rules.save(only, entities.ENTITY_TYPES, actions.ACTIONS) == {} and rules.active() == only
    batches = {"b1": [{"type": "Notice.added", "key": "n1"}, {"type": "Notice.added", "key": "n2"}],
               "b2": [{"type": "Notice.changed", "key": "n1", "changed": ["award_date"]}]}
    d = rules.dry_run(only, batches, actions.ORDER)
    assert d["fired"] == {"awards-only": 2} and d["actions"] == {"apply_notices": {"events": 2, "runs": 1}}
    d = rules.dry_run(list(rules.DEFAULT_RULES), batches, actions.ORDER)
    assert d["actions"]["rebuild_tables"] == {"events": 3, "runs": 2}                  # coalesced per batch
    rules.reset()
    assert rules.active() == list(rules.DEFAULT_RULES) and not rules.customised()


def test_older_reports_below_the_corpus_scope_are_not_new(monkeypatch):
    from procintel.ingestion import wb_client
    listing = [{"id": f"d{i}", "projectid": "P1", "txturl": "t", "docdt": "2026-01-01"} for i in range(150)]

    class Client:
        def __init__(self, **kw):
            pass

        def documents(self, rows, offset, docty_exact):
            return len(listing), listing[offset:offset + rows]
    monkeypatch.setattr(wb_client, "WBClient", Client)
    monkeypatch.setattr(entities, "DOCUMENT_SCOPE", 100)
    rows, complete = entities.documents_from_source({"tracked": ["d5", "d120"]})   # d120 is tracked below the scope
    assert not complete and len(rows) == 101 and "d120" in rows and "d121" not in rows and "d99" in rows


def test_reconcile_logs_what_a_refresh_wrote_and_queues_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    monkeypatch.setattr(jobs_store, "DB_PATH", tmp_path / "jobs.duckdb")
    db_rows = {"n1": {"award_date": None}}
    fake = entities.EntityType("Notice", timedelta(hours=1), ["award_date"], lambda ctx: ({}, False), lambda: dict(db_rows))
    monkeypatch.setattr(entities, "ENTITY_TYPES", {"Notice": fake})
    store.seed("Notice", ["award_date"], db_rows)
    db_rows["n1"] = {"award_date": "2026-10-20"}            # the refresh wrote an award date and a new notice
    db_rows["n2"] = {"award_date": None}
    assert detect.reconcile() == {"Notice": 2}
    assert jobs_store.next_pending() is None                  # nothing queued: the refresh did the work
    assert detect.reconcile() == {"Notice": 0}                # state now matches the database
    assert store.overview()["lastRun"]["Notice"]["note"].startswith("reconciled")


def test_a_failing_source_is_logged_backs_off_and_does_not_stop_the_others(tmp_path, monkeypatch):
    from procintel.pipeline import connectors, eventlog
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    monkeypatch.setattr(jobs_store, "DB_PATH", tmp_path / "jobs.duckdb")
    good = {"n1": {"award_date": None}}

    def broken(ctx):
        raise ConnectionError("source down")
    types = {"Bad": entities.EntityType("Bad", timedelta(hours=1), ["v"], broken, lambda: {"b1": {"v": 1}}, "a broken API"),
             "Notice": entities.EntityType("Notice", timedelta(hours=1), ["award_date"],
                                           lambda ctx: ({k: dict(v) for k, v in good.items()}, False), lambda: dict(good))}
    monkeypatch.setattr(entities, "ENTITY_TYPES", types)
    _run(detect.detect_steps({"force": True}, None, {}))                       # seeds both
    good["n2"] = {"award_date": None}
    out = _run(detect.detect_steps({"force": True}, None, {}))
    assert out["events"] == {"Notice": 1}                                      # the good source still went on
    bad = next(c for c in connectors.status() if c["name"] == "Bad")
    assert bad["lastError"]["message"] == "ConnectionError: source down" and bad["failures"] == 1
    assert bad["lastSuccess"]["note"].startswith("first run") and bad["source"] == "a broken API" and bad["mode"] == "poll"
    assert bad["every"] == "1 hour" and bad["due"] is False
    assert not connectors.due(types["Bad"], force=False)                       # just failed: waits its interval
    et = types["Bad"]
    assert [connectors.wait(et, n) for n in (0, 1, 2, 3)] == [timedelta(hours=1), timedelta(hours=1),
                                                             timedelta(hours=2), timedelta(hours=4)]
    assert connectors.wait(et, 10) == timedelta(days=1)                        # capped at a day
    assert [connectors.words(timedelta(hours=h)) for h in (1, 6, 24, 168, 0.5)] == ["1 hour", "6 hours", "1 day", "7 days", "30 minutes"]

    log = eventlog.batches("Notice")
    assert log["batches"][0]["events"][0]["key"] == "n2" and log["batches"][0]["firings"][0]["jobStatus"]["status"] == "pending"
    assert eventlog.batches("Bad")["batches"] == [] and "Notice.added" in log["types"]


def test_connector_settings_change_interval_on_off_and_reset(tmp_path, monkeypatch):
    from procintel.pipeline import connector_config, connectors
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    et = entities.EntityType("Notice", timedelta(hours=1), ["v"], lambda ctx: ({}, False), lambda: {"a": {"v": 1}}, "src")
    monkeypatch.setattr(entities, "ENTITY_TYPES", {"Notice": et})
    assert connector_config.settings("Notice") == {"mode": "poll", "everyHours": 1.0, "enabled": True}
    connector_config.save("Notice", {"everyHours": 6})
    assert connectors.wait(et, 0) == timedelta(hours=6) and connector_config.customised("Notice")
    assert connectors.wait(et, 3) == timedelta(days=1)                       # backoff from the new interval, capped
    connector_config.save("Notice", {"enabled": False})
    store.log_detection("b0", "Notice", 1, 0)
    assert not connectors.due(et, force=False) and connectors.due(et, force=True)   # off: only "Read now" reads it
    assert connectors.status()[0]["due"] is False and connectors.status()[0]["settings"]["enabled"] is False
    connector_config.save("Notice", {"mode": "push"})
    assert connector_config.every(et) == connector_config.PUSH_RECONCILE    # pushed: polled only to reconcile
    connector_config.save("Notice", {"mode": "poll", "everyHours": 1, "enabled": True})
    assert not connector_config.customised("Notice")                         # saving the defaults is a reset
    for bad in ({"everyHours": 0.01}, {"mode": "fax"}, {"enabled": "yes"}, {"colour": "red"}):
        with pytest.raises(ValueError):
            connector_config.save("Notice", bad)
    with pytest.raises(ValueError):
        connector_config.save("Nope", {})


def test_missing_dates_in_source_rows_are_logged_as_null_and_old_nat_text_reads_as_missing(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    row = {"notice_id": "n1", "award_date": pd.NaT, "price_amount": float("nan"), "notice_date": pd.Timestamp("2026-10-01")}
    ev = store.diff("Notice", ["award_date"], {"n1": row}, {}, complete=False)
    store.record("Notice", "b1", ev, ["n1"])
    con = store.connect()
    logged = _json.loads(con.execute("SELECT new FROM event_log").fetchone()[0])
    con.close()
    assert logged["award_date"] is None and logged["price_amount"] is None and logged["notice_date"].startswith("2026-10-01")
    rows, _ = actions._rows({"n2": {"new": {"notice_id": "n2", "award_date": "NaT", "price_amount": "NaN"}}})
    assert rows[0]["award_date"] is None and rows[0]["price_amount"] is None
