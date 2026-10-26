from datetime import date

import numpy as np
import pandas as pd
import pytest

from procintel.monitoring import forecast, survival


def test_kaplan_meier_by_hand():
    # awards at 10, 20, 30 and two tenders still open at 15 and 25
    times, S = survival.curve([10, 15, 20, 25, 30], [True, False, True, False, True])
    assert list(times) == [10, 20, 30]
    assert S == pytest.approx([4 / 5, 4 / 5 * 2 / 3, 0.0])     # at 20: 3 at risk, 1 award; at 30: the last one
    assert survival.survival_at(times, S, 5) == 1 and survival.survival_at(times, S, 25) == pytest.approx(8 / 15)


def test_remaining_quantile_rule_and_conditioning():
    times, S = survival.curve([10, 15, 20, 25, 30], [True, False, True, False, True])
    assert survival.remaining_quantile(times, S, 0, 0.5) == 30     # first time S <= 0.5
    assert survival.remaining_quantile(times, S, 12, 0.5) == 18     # given open at 12: S(t)/S(12) = 0.67 at 20, 0 at 30
    assert survival.within(times, S, 12, 10) == pytest.approx(1 - (8 / 15) / (4 / 5))
    times2, S2 = survival.curve([10, 50, 60], [True, False, False])  # the tail is censored
    assert survival.remaining_quantile(times2, S2, 20, 0.5) is None   # beyond the data


def test_open_tenders_as_censored_move_the_forecast_later():
    rng = np.random.default_rng(0)
    awarded = pd.DataFrame({"proc_group": "CW", "method_code": "RFB", "tender_to_award_days": rng.integers(40, 200, 60),
                            "contract_duration_days": 300, "phase": None, "age_days": None,
                            "award_date": pd.Timestamp("2025-01-01")})
    still_open = pd.DataFrame({"proc_group": "CW", "method_code": "RFB", "tender_to_award_days": np.nan,
                               "contract_duration_days": np.nan, "phase": "bidding", "age_days": rng.integers(150, 400, 25),
                               "award_date": pd.NaT})
    facts = {"proc_group": "CW", "method_code": "RFB", "tender_start": "2026-07-18", "award_date": None}   # open 100 days
    naive = forecast.forecast(facts, awarded, date(2026, 10, 26))["award"]
    km = forecast.forecast(facts, pd.concat([awarded, still_open], ignore_index=True), date(2026, 10, 26))["award"]
    assert "survival estimate" in km["basis"] and "still open today" in km["basis"]
    assert km["within90"] < naive["within90"]                   # waiting tenders lower the chance of a quick award
