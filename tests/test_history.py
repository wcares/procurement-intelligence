from procintel.insights import history
from procintel.learning import feedback


def _rec(id_, kind):
    return {"id": id_, "kind": kind, "title": id_}


def test_past_recommendations_with_decisions_and_totals_over_everyone(tmp_path):
    db = tmp_path / "f.duckdb"
    req = {"countryCode": "KE", "procGroup": "CW", "methodCode": "RFB"}
    mine = feedback.log_response("recommend", req, {"meta": {}, "recommendations": [
                                 _rec("method:RFQ", "method"), _rec("mitigation:rebid", "mitigation")]}, db, user_id="u1")
    theirs = feedback.log_response("recommend", req, {"meta": {}, "recommendations": [_rec("method:RFQ", "method")]}, db, user_id="u2")
    feedback.log_response("ask", {}, {"meta": {}, "answer": []}, db, user_id="u1")                       # not a recommendation
    feedback.add(mine, "useful", comment="accepted recommendation method:RFQ", db_path=db)
    feedback.add(mine, "not_useful", comment="dismissed recommendation mitigation:rebid", db_path=db)
    feedback.add(theirs, "not_useful", comment="dismissed recommendation method:RFQ", db_path=db)
    out = history.past("u1", db_path=db)
    assert [i["responseId"] for i in out["items"]] == [mine]                                  # only my own
    assert [(r["id"], r["decision"]) for r in out["items"][0]["recommendations"]] == [
        ("method:RFQ", "accepted"), ("mitigation:rebid", "dismissed")]
    assert out["items"][0]["package"]["methodCode"] == "RFB"
    assert out["totals"] == {"method": {"shown": 2, "accepted": 1, "dismissed": 1},
                             "mitigation": {"shown": 1, "accepted": 0, "dismissed": 1}}
