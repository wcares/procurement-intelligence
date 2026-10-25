import duckdb
import numpy as np
import pandas as pd
import pytest

from procintel.prediction import assess, predict


def frame(rows):
    df = pd.DataFrame(rows, columns=["proc_group", "method_code", "tender_to_award_days"])
    for c in ["proc_group", "method_code"]:
        df[c] = df[c].astype("category")
    return df


def test_baseline_falls_back_from_method_to_group_to_all():
    train = frame([("CW", "RFB", d) for d in range(100, 120)] + [("CW", "RFQ", 500)] * 3 + [("GO", "RFQ", 50)] * 5)
    test = frame([("CW", "RFB", 0), ("CW", "RFQ", 0), ("NC", "X", 0)])
    b = predict._baseline(train, test)
    assert b.loc[0, "p50"] == pytest.approx(109.5)              # CW/RFB has 20 rows: its own median
    cw_all = train[train.proc_group == "CW"].tender_to_award_days.median()
    assert b.loc[1, "p50"] == pytest.approx(cw_all)             # CW/RFQ has 3 rows: falls back to all CW
    assert b.loc[2, "p50"] == pytest.approx(train.tender_to_award_days.median())  # NC unseen: all packages


@pytest.fixture(scope="module")
def bundle():
    rng = np.random.default_rng(0)
    n = 300
    df = pd.DataFrame({"proc_group": rng.choice(["CW", "GO"], n), "method_code": rng.choice(["RFB", "RFQ"], n),
                       "region": rng.choice(["Africa", "Asia"], n), "sector": rng.choice(["Transport", None], n),
                       "tender_start": "2022-01-01", "project_id": rng.choice(list("ABCDEFGHIJ"), n)})
    for c in predict.CPIA:
        df[f"cpia_{c}"] = rng.uniform(2, 4, n)
    df["tender_to_award_days"] = np.where(df.proc_group == "CW", 200, 60) + rng.integers(0, 40, n)
    df["value_usd"] = np.where(rng.random(n) < 0.8, 10 ** rng.uniform(4, 7, n), np.nan)  # 80% known, as in the data
    df = predict.add_features(df)
    return predict.train(df, {"days_p50_mae": (10, 20), "days_p90_pinball": (5, 4), "days_p90_coverage": (0.9, 0.9),
                              "over_180_brier": (0.1, 0.2), "over_180_auc": (0.9, 0.5)})


def test_unseen_categories_and_missing_cpia_still_predict(bundle):
    p = predict.predict_one(bundle, {"proc_group": "CS", "method_code": "QCBS", "region": "Mars", "sector": None,
                                     "tender_start": "2026-10-24"})
    assert all(np.isfinite(v) for v in p.values()) and 0 <= p["p_long"] <= 1


def test_model_flags_only_for_targets_that_beat_the_baseline(bundle):
    req = {"procGroup": "CW", "methodCode": "RFB", "countryCode": "KE"}
    flags = assess.model_flags(bundle, req, "Africa", [], {"median": 113})
    assert {f["id"] for f in flags} == {"model-timeline", "model-long"} and all(f["basis"] == "model" for f in flags)
    assert int(flags[0]["label"].split("about ")[1].split()[0]) > 180  # CW is the slow group in this toy data
    bundle_off = {**bundle, "use": {"days_p50": False, "days_p90": False, "over_180": False}}
    assert assess.model_flags(bundle_off, req, "Africa", [], None) == []
    assert assess.model_flags(None, req, "Africa", [], None) == []


def test_cpia_is_taken_as_of_the_tender_year_never_later(tmp_path):
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE package AS SELECT 'k1' package_id, 'P1' project_id, 'CW' proc_group, 'RFB' method_code, "
                "DATE '2020-06-01' tender_start, 100 tender_to_award_days, 'USD' price_currency, 5e5 price_amount, "
                "DATE '2020-09-09' award_date")
    con.execute("CREATE TABLE project AS SELECT 'P1' project_id, 'KE' country_code, 'Transport' sector, 1e6 commitment_usd, DATE '2018-01-01' board_approval")
    con.execute("CREATE TABLE country AS SELECT 'KE' country_code, 'Africa' region")
    con.execute("CREATE TABLE notice_m AS SELECT DATE '2026-09-29' notice_date")  # data snapshot, > 18 months after the tender
    con.execute("CREATE TABLE cpia AS SELECT * FROM (VALUES ('KE', 2018, 'transparency_corruption', 2.0), "
                "('KE', 2020, 'transparency_corruption', 3.0), ('KE', 2023, 'transparency_corruption', 5.0)) t(country_code, year, indicator, value)")
    con.close()
    df = predict.load_frame(db)
    assert df.loc[0, "cpia_transparency_corruption"] == 3.0  # 2020 score; the 2023 one is after the tender


def test_recent_tenders_without_follow_up_are_not_training_rows(tmp_path):
    db = tmp_path / "t.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE package AS SELECT * FROM (VALUES ('old', 'P1', 'CW', 'RFB', DATE '2022-01-01', 300, 'USD', 1e6, DATE '2022-10-28'), "
                "('recent', 'P1', 'CW', 'RFB', DATE '2026-01-01', 40, 'USD', 1e5, DATE '2026-02-10')) "
                "t(package_id, project_id, proc_group, method_code, tender_start, tender_to_award_days, price_currency, price_amount, award_date)")
    con.execute("CREATE TABLE project AS SELECT 'P1' project_id, 'KE' country_code, 'Transport' sector, 1e6 commitment_usd, DATE '2018-01-01' board_approval")
    con.execute("CREATE TABLE country AS SELECT 'KE' country_code, 'Africa' region")
    con.execute("CREATE TABLE cpia AS SELECT 'KE' AS country_code, 2020 AS year, 'transparency_corruption' AS indicator, 3.0 AS value")
    con.execute("CREATE TABLE notice_m AS SELECT DATE '2026-09-29' notice_date")
    con.close()
    assert list(predict.load_frame(db)["package_id"]) == ["old"]  # the 2026 tender has had 9 months, not 18


def test_value_is_optional_and_converted_from_the_estimate(bundle):
    common = {"proc_group": "CW", "method_code": "RFB", "region": "Africa", "sector": None, "tender_start": "2026-10-24"}
    without = predict.predict_one(bundle, common)                       # planner gave no estimate: still predicts
    typical = 10 ** bundle["value_median"]["CW/RFB"]
    assert predict.predict_one(bundle, {**common, "value_usd": typical}) == without   # ...using the typical value
    with_value = predict.predict_one(bundle, {**common, "value_usd": 2_500_000})
    assert all(np.isfinite(v) for v in list(without.values()) + list(with_value.values()))
    assert predict.add_features(pd.DataFrame([{**common, "value_usd": 1000}]))["log_value_usd"].iloc[0] == 3.0
