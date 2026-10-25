import duckdb

from procintel import contract_awards, wgi
from procintel.assess import wgi_flag
from procintel.flag_evidence import WGI_URL, FlagEvidence

CPIA = [{"indicator": "transparency_corruption", "year": 2023, "value": 3.0}]


def cc(value, year=2023):
    return [{"indicator": "control_of_corruption", "year": year, "value": value}]


def test_wgi_flag_only_where_cpia_is_missing_and_corruption_control_is_weak():
    assert wgi_flag(CPIA, cc(-1.5)) is None            # CPIA present: its own flag applies
    assert wgi_flag([], cc(-0.2)) is None              # near the world average
    assert wgi_flag([], cc(-0.7))["level"] == "medium"
    assert wgi_flag([], cc(-1.3))["level"] == "high"
    assert wgi_flag([], []) is None


def test_wgi_flag_evidence_points_at_the_indicator():
    fe = FlagEvidence.__new__(FlagEvidence)
    fe.packages, fe.events = [], {}
    [f] = fe.attach([{"id": "governance-wgi"}], {"countryCode": "PE", "procGroup": "CW", "methodCode": "RFB"},
                    {}, None, [], cc(-0.8))
    assert f["evidence"][0]["ref"] == "GOV_WGI_CC.EST" and f["evidence"][0]["url"] == WGI_URL


def test_latest_keeps_the_newest_year_per_indicator(tmp_path):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    con.execute("CREATE TABLE wgi (country_code VARCHAR, year INT, indicator VARCHAR, value DOUBLE)")
    con.execute("INSERT INTO wgi VALUES ('PE', 2021, 'rule_of_law', -0.5), ('PE', 2023, 'rule_of_law', -0.444)")
    assert wgi.latest(con) == {"PE": [{"indicator": "rule_of_law", "year": 2023, "value": -0.44}]}


def test_signing_date_fills_only_missing_awards_after_tender_start(tmp_path):
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("""CREATE TABLE package (package_id VARCHAR, project_id VARCHAR, tender_start TIMESTAMPTZ,
                   award_date TIMESTAMPTZ, tender_to_award_days INT)""")
    con.execute("""INSERT INTO package VALUES ('P1/KE-1', 'P1', '2022-01-01', NULL, NULL),
                   ('P1/KE-2', 'P1', '2022-01-01', '2022-03-01', 59), ('P1/KE-3', 'P1', '2022-06-01', NULL, NULL)""")
    con.execute("CREATE TABLE contract_award (project_id VARCHAR, contract_ref VARCHAR, signing_date DATE)")
    con.execute("""INSERT INTO contract_award VALUES ('P1', 'ke-1', '2022-02-10'), ('P1', 'KE-2', '2022-04-01'),
                   ('P1', 'KE 3', '2022-05-01')""")
    con.close()
    assert contract_awards.fill_award_dates(db) == 1
    con = duckdb.connect(str(db))
    rows = dict(con.execute("SELECT package_id, tender_to_award_days FROM package").fetchall())
    assert rows == {"P1/KE-1": 40, "P1/KE-2": 59, "P1/KE-3": None}   # KE-3 signed before its tender: left empty
