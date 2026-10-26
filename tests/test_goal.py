import numpy as np
import pandas as pd

from procintel.prediction import goal

# goods: RFQ packages small and fast (20..39 days), RFB packages larger and slower (60..200 days)
H = pd.DataFrame(
    [{"proc_group": "GO", "method_code": "RFQ", "tender_to_award_days": 20 + i, "log_value_usd": 4.5 + 0.02 * i,
      "region": "R1"} for i in range(20)] +
    [{"proc_group": "GO", "method_code": "RFB", "tender_to_award_days": 60 + 7 * i, "log_value_usd": 5.5 + 0.05 * i,
      "region": "R1" if i % 2 else "R2"} for i in range(21)] +
    [{"proc_group": "GO", "method_code": "DIR", "tender_to_award_days": 10, "log_value_usd": 5.0, "region": "R1"}])


def test_set_ups_ranked_by_how_often_they_met_the_target_with_value_flags():
    r = goal.options(H, {"procGroup": "GO", "estimatedValueUsd": 1_000_000}, 90, "R1", [], None, {"RFQ": "Request for Quotations"}, 2)
    assert [o["method"] for o in r["options"]] == ["RFB", "RFB", "RFQ", "RFQ"]          # DIR: fewer than 10 packages
    rfq = [o for o in r["options"] if o["method"] == "RFQ"]
    assert all(o["share"] == 1.0 and "check the Procurement Regulations" in o["flag"] for o in rfq)   # fast but too big
    one = next(o for o in r["options"] if o["method"] == "RFB" and o["lots"] == 1)
    assert one["lotValueUsd"] == 1_000_000 and one["n"] >= 10 and 0 < one["share"] < 1 and "flag" not in one
    assert len(r["caveats"]) == 2 and r["note"] is None


def test_without_a_value_only_the_method_varies_and_regions_narrow_when_they_can():
    r = goal.options(H, {"procGroup": "GO"}, 50, "R2", [], None, None)
    assert {o["lots"] for o in r["options"]} == {1} and "estimated value" in r["note"]
    rfb = next(o for o in r["options"] if o["method"] == "RFB")
    assert rfb["scope"] == "GO via RFB, R2" and rfb["n"] == 11                         # 11 RFB packages in R2
    assert goal.options(H, {"procGroup": "CW"}, 50, None, [], None, None)["options"] == []   # nothing for works here
