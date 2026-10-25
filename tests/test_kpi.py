from procintel import feedback, kpi


def test_weekly_kpis_from_logged_responses_and_ratings(tmp_path):
    db = tmp_path / "fb.duckdb"
    a1 = feedback.log_response("ask", {"question": "q"}, {"unsupported": True, "citations": [], "meta": {}}, db_path=db)
    a2 = feedback.log_response("ask", {"question": "q"}, {"unsupported": False, "citations": [{"id": "d:1"}], "meta": {}}, db_path=db)
    s1 = feedback.log_response("assess", {"countryCode": "KE"}, {"precedents": [], "meta": {}}, db_path=db)
    feedback.add(a2, "useful", db_path=db)
    feedback.add(s1, "not_useful", db_path=db)
    feedback.add(a2, "bad_citation", citation_id="d:1", db_path=db)
    [w] = kpi.weekly(db)
    assert (w["ask"], w["assess"]) == (2, 1) and w["ask_refusal_rate"] == 0.5
    assert w["rated_share"] == round(2 / 3, 3) and w["useful_share"] == 0.5 and w["citations_flagged"] == 1
    assert kpi.weekly(tmp_path / "missing.duckdb") == []
