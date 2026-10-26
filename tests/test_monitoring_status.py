from datetime import date

import pandas as pd
import pytest

from procintel.core import paths
from procintel.monitoring import status, status_rules

TODAY = date(2026, 10, 26)


def pkg(pid, group="CW", method="RFB", tender=None, award=None, days=None, dur=None, rebid=None, project="P1",
        pstatus="Active", closing="2030-01-01", icr=False, first=None):
    return {"package_id": pid, "project_id": project, "proc_group": group, "method_code": method, "description": pid,
            "tender_start": pd.Timestamp(tender) if tender else pd.NaT, "award_date": pd.Timestamp(award) if award else pd.NaT,
            "tender_to_award_days": days, "contract_duration_days": dur, "rebid_evidence": rebid,
            "first_notice": pd.Timestamp(first or tender) if (first or tender) else pd.NaT, "last_notice": pd.NaT,
            "n_notices": 1, "project_name": project, "country_code": "KE", "project_status": pstatus,
            "closing_date": pd.Timestamp(closing) if closing else pd.NaT, "has_completion_report": icr}


@pytest.fixture
def history():
    # 20 awarded civil-works packages that took 100..290 days: the 99th percentile is about 288 days
    return [pkg(f"h{i}", tender="2020-01-01", award="2020-06-01", days=100 + 10 * i, dur=200) for i in range(20)]


def test_each_rule_in_order(history):
    rows = history + [
        pkg("open-young", tender="2026-08-01"),                                  # 86 days, within the limit
        pkg("open-old", tender="2025-09-01"),                                    # 420 days: past the 99th percentile
        pkg("running", tender="2026-01-01", award="2026-05-01", dur=400),        # contract until 2027
        pkg("ended", tender="2023-01-01", award="2023-06-01", dur=100),          # ended long ago
        pkg("no-duration", tender="2019-01-01", award="2019-06-01"),             # median 200 days: ended (estimate)
        pkg("replaced", tender="2026-09-01", rebid="successor_reference"),
        pkg("icr-open", tender="2026-09-01", project="P2", icr=True),            # project ended, never awarded
        pkg("no-dates"),
    ]
    c = status.classify(pd.DataFrame(rows), status_rules.DEFAULTS, TODAY).set_index("package_id")
    got = {k: (c.loc[k, "status"], c.loc[k, "phase"]) for k in
           ["open-young", "open-old", "running", "ended", "no-duration", "replaced", "icr-open", "no-dates"]}
    assert got == {"open-young": ("active", "bidding"), "open-old": ("stale", None), "running": ("active", "contract"),
                   "ended": ("finished", None), "no-duration": ("finished", None), "replaced": ("replaced", None),
                   "icr-open": ("stale", None), "no-dates": ("stale", None)}
    assert "estimate" in c.loc["no-duration", "reason"] and "without a recorded award" in c.loc["icr-open", "reason"]
    assert c.loc["open-old", "stale_limit_days"] < 300 and c.loc["running", "contract_end"] == "2027-06-05"


def test_parameters_move_packages_and_the_dry_run_counts_them(history, tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "STATUS_RULES", tmp_path / "status_rules.json")
    df = pd.DataFrame(history + [pkg("open-mid", tender="2026-04-01")])             # 208 days open
    assert status.classify(df, status_rules.active(), TODAY).set_index("package_id").loc["open-mid", "status"] == "active"
    d = status.dry_run(df, {"stale_max_days": 180}, TODAY)
    assert d["moves"] == [{"from": "active", "to": "stale", "packages": 1}]
    status_rules.save({"stale_max_days": 180})
    assert status_rules.customised() and status_rules.active()["stale_max_days"] == 180
    status_rules.save(dict(status_rules.DEFAULTS))                                  # saving the defaults is a reset
    assert not status_rules.customised()
    for bad in ({"stale_quantile": 1.5}, {"stale_max_days": 5}, {"project_overrides": ["moon"]}, {"x": 1}):
        with pytest.raises(ValueError):
            status_rules.save(bad)


def test_rollup_counts_packages_per_project(history):
    c = status.classify(pd.DataFrame(history + [pkg("a", project="P9", tender="2026-09-01")]), status_rules.DEFAULTS, TODAY)
    p9 = next(r for r in status.rollup(c) if r["projectId"] == "P9")
    assert p9["packages"]["active"] == 1 and p9["bidding"] == 1


def test_ongoing_projects_are_active_open_recent_with_notices_and_not_tracked(tmp_path, monkeypatch):
    import duckdb
    from procintel.ingestion import ongoing
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "m.duckdb")
    con = duckdb.connect(str(tmp_path / "m.duckdb"))
    con.execute("CREATE TABLE projects AS SELECT 'P0' AS project_id")
    con.close()

    class Client:
        def projects(self, rows, offset, status_exact):
            if offset:
                return 0, []
            return 5, [{"id": "P0", "closingdate": "12/31/2030", "boardapprovaldate": "2024-12-01T00:00:00Z"},   # tracked
                       {"id": "P1", "closingdate": "12/31/2030", "boardapprovaldate": "2024-12-01T00:00:00Z"},   # good
                       {"id": "P2", "closingdate": "1/31/2025", "boardapprovaldate": "2024-12-01T00:00:00Z"},    # closed
                       {"id": "P3", "closingdate": "12/31/2030", "boardapprovaldate": "2019-01-01T00:00:00Z"},   # old
                       {"id": "P4", "closingdate": "12/31/2030", "boardapprovaldate": "2024-11-01T00:00:00Z"}]   # few notices

        def notices(self, rows, project_id):
            return (3 if project_id == "P4" else 40), []
    assert [p["id"] for p in ongoing.choose(5, Client(), TODAY)] == ["P1"]
