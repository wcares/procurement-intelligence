from procintel.learning import feedback, kpi


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


def test_users_response_times_and_award_error(tmp_path):
    import duckdb
    from procintel.learning import feedback, kpi
    fdb, mdb = tmp_path / "feedback.duckdb", tmp_path / "main.duckdb"
    pred = lambda d, basis="model": {"meta": {}, "prediction": {"basis": basis, "days_p50": d}}  # noqa: E731
    feedback.log_response("assess", {"tenderReference": "ke-kura-1 "}, pred(100), fdb, user_id="u1", duration_ms=20000)
    feedback.log_response("assess", {"tenderReference": "KE-KURA-2"}, pred(150, "historical median"), fdb,
                          user_id="u2", duration_ms=70000)
    feedback.log_response("assess", {"tenderReference": "NOT-AWARDED"}, pred(90), fdb, user_id="u1", duration_ms=30000)
    feedback.log_response("ask", {}, {"meta": {}, "unsupported": False}, fdb, user_id="u1", duration_ms=40000)
    [w] = kpi.weekly(fdb)
    assert w["active_users"] == 2 and w["median_seconds"] == 35.0 and w["over_minute_share"] == 0.25
    con = duckdb.connect(str(mdb))
    con.execute("CREATE TABLE package AS SELECT * FROM (VALUES ('P1/KE-KURA-1', 130), ('P1/KE-KURA-2', 110), "
                "('P1/NOT-AWARDED', NULL)) t(package_id, tender_to_award_days)")
    con.close()
    e = kpi.award_error(fdb, mdb)
    assert (e["named"], e["matched"], e["pending"]) == (3, 2, 1)
    assert e["model"] == {"n": 1, "mean_abs_error_days": 30.0}                      # predicted 100, took 130
    assert e["historical median"] == {"n": 1, "mean_abs_error_days": 40.0}          # reference matched without case
