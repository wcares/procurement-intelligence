import duckdb
import pytest

from procintel.insights import dashboard


@pytest.fixture
def board(tmp_path):
    db = tmp_path / "m.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE country AS SELECT * FROM (VALUES ('AA', 'Aland', 'R1'), ('BB', 'Bland', 'R1')) t(country_code, name, region)")
    con.execute("""CREATE TABLE project AS SELECT * FROM (VALUES
        ('P1', 'One', 'AA', 'Rural and Inter-Urban Roads', DATE '2020-06-30'),
        ('P2', 'Two', 'AA', 'Health', DATE '2021-06-30'),
        ('P3', 'Three', 'AA', 'Health', DATE '2021-06-30'),
        ('P4', 'Four', 'BB', 'Health', DATE '2022-06-30')) t(project_id, name, country_code, sector, closing_date)""")
    con.execute("""CREATE TABLE package AS SELECT * FROM (VALUES
        ('P1/a', 'P1', 'CW', 'RFB', 'road', 400, TIMESTAMPTZ '2019-01-01'),
        ('P2/b', 'P2', 'CW', 'RFB', 'clinic', 100, TIMESTAMPTZ '2019-02-01'),
        ('P3/c', 'P3', 'GO', 'RFQ', 'drugs', 50, TIMESTAMPTZ '2020-01-01'),
        ('P4/d', 'P4', 'CW', 'RFB', 'clinic', 300, TIMESTAMPTZ '2020-03-01'),
        ('P4/e', 'P4', 'CW', 'RFB', 'clinic', NULL, TIMESTAMPTZ '2020-03-01'))
        t(package_id, project_id, proc_group, method_code, description, tender_to_award_days, tender_start)""")
    con.execute("CREATE TABLE project_evidence AS SELECT * FROM (VALUES ('rebid', 'P1', 'icr', 'x', 'q')) t(kind, project_id, source, ref, quote)")
    con.execute("CREATE TABLE document_project AS SELECT * FROM (VALUES ('d1', 'P1'), ('d4', 'P4')) t(doc_id, project_id)")
    con.execute("CREATE TABLE procurement_check AS SELECT * FROM (VALUES ('d1', 'Moderately Unsatisfactory'), ('d4', 'Satisfactory')) t(doc_id, lowest)")
    con.execute("CREATE TABLE chunk AS SELECT * FROM (VALUES ('d1:1', 'd1'), ('d1:2', 'd1'), ('d4:1', 'd4')) t(chunk_id, doc_id)")
    con.execute("CREATE TABLE chunk_problem AS SELECT * FROM (VALUES ('d1:1', true, 'funding or payment delays'), ('d1:2', true, 'funding or payment delays'), ('d4:1', false, NULL)) t(chunk_id, problem, kind)")
    con.close()
    return dashboard.Dashboard(db)


def test_ranking_worst_first_with_counts_and_few_flag(board):
    r = board.ranking("delay", "country")
    assert [(x["key"], x["value"], x["n"], x["projects"], x["few"]) for x in r["rows"]] == [
        ("AA", 100.0, 3, 3, False), ("BB", 300.0, 1, 1, True)]               # BB is slower but behind 1 project
    assert r["rows"][0]["label"] == "Aland"
    assert board.ranking("rebid", "country")["rows"][0]["value"] == pytest.approx(1 / 3, abs=0.001)
    assert board.ranking("procurement_rating", "country")["rows"][0]["value"] == 1.0   # P1 rated below satisfactory
    with pytest.raises(ValueError):
        board.ranking("rebid", "method")                                     # a project measure has no method


def test_trends_heatmap_records_and_summary(board):
    t = board.trends()
    assert [(a["year"], a["median_days"], a["n"]) for a in t["award"]] == [(2019, 250.0, 2), (2020, 175.0, 2)]
    assert t["problems"] == [{"year": 2020, "per_project": 2.0, "projects": 1}, {"year": 2022, "per_project": 0.0, "projects": 1}]
    cells = board.heatmap("delay", min_n=1)["cells"]
    assert {(c["country"], c["method"], c["value"]) for c in cells} == {("AA", "RFB", 250.0), ("AA", "RFQ", 50.0), ("BB", "RFB", 300.0)}
    recs = board.records("country", "AA", "delay")["records"]
    assert [r["packageId"] for r in recs] == ["P1/a", "P2/b", "P3/c"]                # slowest first, awarded only
    assert board.summary()["awarded"] == 4 and board.problem_mix()["kinds"] == [{"kind": "funding or payment delays", "passages": 2}]


def test_stage_durations_by_group_and_risks_placed():
    from procintel.prediction import stages
    stats = {"all": {"bidding": {"median": 100.0, "p90": 300.0, "n": 50}},
             "CW": {"bidding": {"median": 120.0, "p90": 350.0, "n": 30}, "contract": {"median": 270.0, "p90": 560.0, "n": 40}}}
    rows = {r["key"]: r for r in stages.for_package(stats, "CW", "RFB")}
    assert [r["key"] for r in stages.for_package(stats, "CW", "RFB")] == ["plan", "bidding", "signing", "contract"]
    assert rows["bidding"]["median"] == 120.0 and rows["bidding"]["scope"] == "all Civil Works packages"   # no CW/RFB
    assert rows["plan"]["median"] is None and rows["signing"]["n"] == 0                                    # no dates
    placed = stages.place_risks([{"id": "rebid"}, {"id": "amendment"}, {"id": "governance"}, {"id": "new-kind"}])
    assert [r["stage"] for r in placed] == ["bidding", "contract", "all", "all"]
    assert stages.stage_of_problem("weak specifications or design") == "plan" and stages.stage_of_problem(None) is None
