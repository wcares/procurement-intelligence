from procintel import assess, rebid


def test_reports_vs_advice():
    assert rebid.reports("The contractor became insolvent, requiring CDR to re-bid the remaining sections.")
    assert rebid.reports("The first procurement attracted no responsive bids and was relaunched.")
    assert not rebid.reports("This could change how the procurement unit packages its contracts or reduces retendering.")
    assert not rebid.reports("Procurement was completed on time.")


INFO = {"BD": {"projects": 5, "with_rebid": 3, "example": ("P1", "contracts were terminated and re-tendered")},
        "KE": {"projects": 2, "with_rebid": 0, "example": None}}


def test_flag_states_a_lower_bound_with_the_overall_figure():
    f = assess.rebid_flag(INFO, "BD", "Bangladesh", (350.0, 108.0))
    assert f["label"] == "Re-tendering in past projects: at least 3 of 5" and f["level"] == "high" and f["basis"] == "statistic"
    assert "across all 7 projects in the data, at least 3 (43%)" in f["detail"] and "median of 350 days" in f["detail"]


def test_no_evidence_is_not_presented_as_no_risk():
    f = assess.rebid_flag(INFO, "KE", "Kenya")
    assert f["level"] == "low" and "not evidence of absence" in f["detail"]
    assert assess.rebid_flag(INFO, "XX", "") is None and assess.rebid_flag({}, "KE", "Kenya") is None
