from datetime import date

import pandas as pd

from procintel.monitoring import forecast, isr_ratings

TODAY = date(2026, 10, 26)
# 40 awarded civil-works RFB tenders: 50, 60, ..., 440 days; contracts of 300 days
HISTORY = pd.DataFrame({"proc_group": ["CW"] * 40, "method_code": ["RFB"] * 40,
                        "tender_to_award_days": [50 + 10 * i for i in range(40)], "contract_duration_days": [300] * 40})


def test_a_tender_open_100_days_is_forecast_from_the_tenders_still_open_at_100():
    f = forecast.forecast({"proc_group": "CW", "method_code": "RFB", "tender_start": "2026-07-18", "award_date": None,
                           "closing_date": "2030-01-01"}, HISTORY, TODAY)
    assert f["stages"][0] == {"stage": "bidding", "start": "2026-07-18", "status": "in progress", "elapsedDays": 100}
    a = f["award"]
    # still open at 100 days: 110..440, i.e. 10..340 more; median 175 more days
    assert a["medianDays"] == 175 and "n=34" in a["basis"] and a["within30"] == 0.09
    assert f["stages"][1]["stage"] == "contract" and f["stages"][1]["status"] == "forecast" and f["stages"][1]["durationDays"] == 300
    assert f["warnings"] == [] and any("leans early" in c for c in f["caveats"])


def test_warnings_slow_reissued_after_closing_and_isr_downgrade():
    isr = {"date": "2026-04-07", "downgrades": ["Overall Implementation Progress (IP): Satisfactory -> Moderately Satisfactory"]}
    f = forecast.forecast({"proc_group": "CW", "method_code": "RFB", "tender_start": "2025-07-01", "award_date": None,
                           "reissued": True, "closing_date": "2027-01-01"}, HISTORY, TODAY, isr)
    kinds = [w["kind"] for w in f["warnings"]]
    assert kinds == ["slow", "reissued", "after_closing", "isr_downgrade"]          # open 482 days > the 90th percentile
    assert f["award"] is None                                                       # nobody was still open that long


def test_an_awarded_package_runs_its_stated_contract_and_too_little_history_says_so():
    f = forecast.forecast({"proc_group": "CW", "method_code": "RFB", "tender_start": "2026-01-01", "award_date": "2026-05-01",
                           "contract_duration_days": 400, "closing_date": "2030-01-01"}, HISTORY, TODAY)
    assert f["stages"][0]["status"] == "done" and f["contractEnd"] == "2027-06-05" and f["stages"][1]["status"] == "in progress"
    g = forecast.forecast({"proc_group": "GO", "method_code": "RFQ", "tender_start": "2026-09-01", "award_date": None}, HISTORY, TODAY)
    assert g["award"] is None and "not enough" in " ".join(g["caveats"]).lower() or "Fewer than" in " ".join(g["caveats"])
    assert forecast.forecast({"proc_group": "CW", "method_code": "RFB"}, HISTORY, TODAY)["stages"] == []   # no dates


def test_isr_ratings_and_downgrades():
    t = ("Name Previous Current Progress towards achievement of PDO Satisfactory Moderately Satisfactory Overall "
         "Implementation Progress (IP) Moderately Satisfactory Moderately Satisfactory Overall Risk Rating Moderate Substantial")
    r = isr_ratings.parse(t)
    assert r == {"pdo": ("Satisfactory", "Moderately Satisfactory"), "ip": ("Moderately Satisfactory", "Moderately Satisfactory"),
                 "risk": ("Moderate", "Substantial")}
    assert isr_ratings.downgrades(r) == ["Progress towards achievement of PDO: Satisfactory -> Moderately Satisfactory",
                                         "Overall Risk Rating: Moderate -> Substantial"]
