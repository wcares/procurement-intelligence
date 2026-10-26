import duckdb
import pytest
from fastapi.testclient import TestClient

from procintel.core import paths
from procintel.insights import alerts
from procintel.pipeline import actions, rules


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "main.duckdb")
    monkeypatch.setattr(paths, "PIPELINE_DB", tmp_path / "pipeline.duckdb")
    con = duckdb.connect(str(tmp_path / "main.duckdb"))
    con.execute("CREATE TABLE projects AS SELECT * FROM (VALUES ('P1', 'Roads', 'Republic of Kenya', 'KE', "
                "'Eastern and Southern Africa', 'Transport'), ('P2', 'Schools', 'Republic of Ghana', 'GH', "
                "'Western and Central Africa', 'Education')) t(project_id, name, country, country_code, region, sector)")
    con.execute("CREATE TABLE package AS SELECT * FROM (VALUES ('P1/B1', 240), ('P1/B2', 90)) t(package_id, tender_to_award_days)")
    con.execute("CREATE TABLE documents AS SELECT 'd9' AS doc_id, 'P2' AS project_id, 'ICR Schools' AS title")
    con.close()


def notice(key, project, group, kind="Invitation for Bids", version=0, bid="B1"):
    return {"type": "Notice.added", "key": key, "changed": [],
            "new": {"project_id": project, "proc_group": group, "method_code": "RFB", "notice_type": kind,
                    "notice_version": version, "bid_ref": bid, "description": f"notice {key}"}}


def test_a_watch_list_is_a_scope_and_projects_match_on_their_own():
    w = {"country": {"KE"}, "proc_group": {"CW"}}
    assert alerts.in_scope(w, {"country_code": "KE", "proc_group": "CW"})
    assert not alerts.in_scope(w, {"country_code": "KE", "proc_group": "GO"})          # all kinds must match
    assert alerts.in_scope({"project": {"P2"}}, {"project_id": "P2", "country_code": "GH"})
    assert not alerts.in_scope({}, {"country_code": "KE"})                              # an empty list watches nothing


def test_batch_events_become_one_alert_per_planner_and_kind(world):
    alerts.set_watch("ana", {"country": ["KE"], "proc_group": ["CW"]})
    alerts.set_watch("ben", {"project": ["P2"]})
    events = {"n1": notice("n1", "P1", "CW"), "n2": notice("n2", "P1", "CW", version=2),
              "n3": notice("n3", "P1", "GO"),                                            # goods: not in ana's scope
              "n4": notice("n4", "P1", "CW", kind="Contract Award", bid="B1"),
              "n5": {"type": "Notice.changed", "key": "n5", "changed": ["award_date"],
                     "new": notice("n5", "P1", "CW", bid="B2")["new"]}}
    assert alerts.from_events(events, {"d9": {"project_id": "P2", "title": "ICR Schools"}}) == 4
    a = {x["kind"]: x for x in alerts.recent("ana")["alerts"]}
    assert set(a) == {"new_notices", "reissued", "awarded"}
    assert a["new_notices"]["title"] == "3 new procurement notices in Republic of Kenya"
    assert a["new_notices"]["detail"] == "2 Invitation for Bids, 1 Contract Award"
    assert a["awarded"]["title"] == "2 awards recorded in Republic of Kenya"
    assert a["awarded"]["detail"] == ("1 of the 2 with a known award time took longer than 180 days from tender to "
                                      "award: 240 days")
    b = alerts.recent("ben")
    assert [x["kind"] for x in b["alerts"]] == ["report"] and b["unread"] == 1
    alerts.set_watch("cy", {"country": ["KE"]})                                          # an award with no tender notice
    alerts.from_events({"n6": notice("n6", "P1", "CW", kind="Contract Award", bid="B9")}, {})
    cy = {x["kind"]: x for x in alerts.recent("cy")["alerts"]}
    assert cy["awarded"]["detail"].startswith("award times not known")
    alerts.mark_read("ben")
    assert alerts.recent("ben")["unread"] == 0
    with pytest.raises(ValueError):
        alerts.set_watch("ana", {"colour": ["red"]})


def test_the_rule_and_action_reach_uploaded_reports(world):
    plan, _ = rules.plan([{"type": "Upload.ingested", "key": "upload-x"}], rules.DEFAULT_RULES, actions.ORDER)
    assert "watch_alerts" in [a for a, _ in plan]
    assert actions.ORDER.index("watch_alerts") > actions.ORDER.index("rebuild_tables")   # award times are current
    alerts.set_watch("ben", {"project": ["P2"]})
    actions.watch_alerts(["d9"], {"d9": {"type": "Document.added", "key": "d9", "new": {}}}, {})
    assert alerts.recent("ben")["alerts"][0]["title"] == "1 new completion report"


def test_insights_endpoints(world):
    from procintel.api.app import app
    c = TestClient(app)
    r = c.put("/insights/watch", json={"watch": {"country": ["KE"], "method": ["RFB"]}}).json()
    assert r["watch"]["country"] == ["KE"] and c.get("/insights/watch").json()["watch"]["method"] == ["RFB"]
    assert c.put("/insights/watch", json={"watch": {"x": ["1"]}}).status_code == 400
    assert c.get("/insights/alerts").json() == {"alerts": [], "unread": 0}


def test_method_alternatives_need_a_clear_gap_and_enough_packages():
    from procintel.insights import recommendations as rec
    bench = {"CW/RFB": {"n": 50, "median": 200}, "CW/RFQ": {"n": 40, "median": 100}, "CW/DIR": {"n": 5, "median": 20},
             "CW/LIB": {"n": 30, "median": 180}, "GO/RFQ": {"n": 30, "median": 10}}
    out = rec.method_alternatives(bench, "CW", "RFB", {"RFQ": "Request for Quotations", "RFB": "Request for Bids"})
    assert [r["id"] for r in out] == ["method:RFQ"]            # DIR too few packages, LIB only 10% faster, GO another group
    assert "median 100 days" in out[0]["text"] and "(n=40)" in out[0]["text"] and "thresholds" in out[0]["note"]
    assert rec.method_alternatives(bench, "CW", "XYZ", {}) == []


def test_mitigations_come_only_from_supported_answers(monkeypatch):
    from procintel.insights import recommendations as rec
    asked = []

    def fake_ask(r, q, proc_group=None):
        asked.append(q)
        if "amendments" in q:
            return {"unsupported": True, "answer": [], "citations": []}
        return {"unsupported": False, "answer": [{"text": "They pre-qualified bidders.", "citations": [0]}],
                "citations": [{"id": "c1"}]}
    monkeypatch.setattr(rec.answer, "ask", fake_ask)
    risks = [{"id": "low1", "label": "Minor", "level": "low"}, {"id": "amend", "label": "Contract amendments", "level": "medium"},
             {"id": "slow", "label": "Award takes longer than 6 months", "level": "high"},
             {"id": "x", "label": "Third", "level": "medium"}]
    out = rec.mitigations(None, risks, "CW")
    assert len(asked) == 2 and "award takes longer than 6 months" in asked[0]     # high first, at most two, no low
    assert [r["risk"] for r in out] == ["slow"]                                    # the unsupported one gives nothing


def test_a_watch_list_can_follow_a_region(world):
    alerts.set_watch("dee", {"region": ["Eastern and Southern Africa"], "proc_group": ["CW"]})
    assert alerts.get_watch("dee")["region"] == ["Eastern and Southern Africa"]
    events = {"n1": notice("n1", "P1", "CW"), "n2": notice("n2", "P2", "CW")}       # Kenya in the region, Ghana not
    assert alerts.from_events(events, {}) == 1
    [a] = alerts.recent("dee")["alerts"]
    assert a["title"] == "1 new procurement notice in Republic of Kenya"


def test_award_times_shifting_in_a_scope_alert_once_a_month(world, tmp_path):
    from datetime import datetime, timedelta
    now = datetime(2026, 10, 26)
    rows = [(f"P1/R{i}", "P1", "CW", "RFB", 150, (now - timedelta(days=30 + i)).isoformat()) for i in range(8)]   # recent
    rows += [(f"P1/B{i}", "P1", "CW", "RFB", 100, (now - timedelta(days=400 + 20 * i)).isoformat()) for i in range(15)]
    rows += [(f"P2/G{i}", "P2", "CW", "RFB", 300, (now - timedelta(days=30)).isoformat()) for i in range(8)]  # Ghana
    con = duckdb.connect(str(tmp_path / "main.duckdb"))
    con.execute("DROP TABLE package")
    con.execute("CREATE TABLE package (package_id VARCHAR, project_id VARCHAR, proc_group VARCHAR, method_code VARCHAR, "
                "tender_to_award_days INTEGER, award_date TIMESTAMP)")
    con.executemany("INSERT INTO package VALUES (?, ?, ?, ?, ?, ?)", rows)
    con.close()
    alerts.set_watch("ana", {"region": ["Eastern and Southern Africa"]})
    alerts.set_watch("ben", {"country": ["GH"]})                                          # too few awards before
    assert alerts.award_shifts(now=now) == 1
    [a] = alerts.recent("ana")["alerts"]
    assert a["kind"] == "award_shift" and a["title"] == "Award times for RFB in your watch-list rose 50%"
    assert a["detail"].startswith("median 150 days from tender to award for the 8 awards recorded in the last 12 months, "
                                  "against 100 days for the 15")
    assert alerts.award_shifts(now=now + timedelta(days=5)) == 0                          # not again within a month
    assert alerts.award_shifts(now=now + timedelta(days=31)) == 1


def test_the_award_change_event_reaches_the_shift_check(world, monkeypatch):
    called = []
    monkeypatch.setattr(alerts, "award_shifts", lambda: called.append(1))
    plan, _ = rules.plan([{"type": "Package.award_changed", "key": "all"}], rules.DEFAULT_RULES, actions.ORDER)
    assert ("watch_alerts", ["all"]) in plan
    actions.watch_alerts(["all"], {}, {})
    assert called == [1]
