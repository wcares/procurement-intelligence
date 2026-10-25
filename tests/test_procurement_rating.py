from procintel.prediction import procurement_rating as pr


def test_closing_rating_and_conflict_with_a_satisfactory_outcome():
    p = pr.parse(["Procurement performance was rated Satisfactory at entry but declined over time, "
                  "reaching Moderately Unsatisfactory by 2025. FM was Satisfactory."])
    assert p["closing"] == "Moderately Unsatisfactory" and p["lowest"] == "Moderately Unsatisfactory"
    c = pr.check(p, "Satisfactory", None)
    assert c["conflict"] and "as low as Moderately Unsatisfactory" in c["note"] and "reaching" in c["note"]


def test_abbreviations_and_recovery_by_closing():
    p = pr.parse(["Procurement performance remained mostly Moderately Satisfactory (MS) with temporary deterioration "
                  "to MU in 2024, followed by a steady recovery to Satisfactory by project closing."])
    assert p["lowest"] == "Moderately Unsatisfactory" and p["closing"] == "Satisfactory"
    assert "(at closing: Satisfactory)" in pr.check(p, "Satisfactory", None)["note"]


def test_mixed_ratings_without_a_closing_sentence_leave_closing_unknown():
    p = pr.parse(["Procurement performance fluctuated between Satisfactory and Moderately Satisfactory."])
    assert p["closing"] is None and p["lowest"] == "Moderately Satisfactory"
    assert not pr.check(p, "Satisfactory", None)["conflict"]  # never on the unsatisfactory side


def test_not_a_performance_rating_or_a_count_over_sub_projects():
    assert pr.parse(["Procurement arrangements were acceptable, and the capacity assessment was satisfactory."]) is None
    assert pr.parse(["The proportion of projects with Satisfactory and Moderate Unsatisfactory ratings for "
                     "Procurement was high - 51 and 41 projects respectively."]) is None


def test_unsatisfactory_procurement_under_an_unsatisfactory_outcome_is_not_a_conflict():
    p = pr.parse(["At closing, the Procurement performance was rated Unsatisfactory."])
    assert not pr.check(p, "Highly Unsatisfactory", None)["conflict"]
    assert pr.check(p, None, "Moderately Satisfactory")["conflict"]  # falls back to the last IP rating
    assert not pr.check(p, None, None)["conflict"]
