from procintel import feedback, feedback_review as fr


def ask(db, question, unsupported=False, cites=("d:1",)):
    return feedback.log_response("ask", {"question": question},
                                 {"unsupported": unsupported, "citations": [{"id": c} for c in cites], "meta": {}},
                                 db_path=db)


def test_review_lists_flags_refusals_and_not_useful_and_demotes_after_two_responses(tmp_path, monkeypatch):
    db = tmp_path / "fb.duckdb"
    monkeypatch.setattr(fr, "DEMOTE_MIN", 2)
    r1, r2 = ask(db, "Why were contracts terminated?"), ask(db, "Why were bids cancelled?")
    ask(db, "Who won the World Cup?", unsupported=True)
    feedback.add(r1, "bad_citation", "d:1", "about roads, not contracts", db_path=db)
    feedback.add(r1, "bad_citation", "d:1", db_path=db)                     # same response twice: counts once
    out = fr.build(db)
    assert out["items"] == {"flagged_citation": 1, "refused_question": 1, "not_useful": 0} and out["demoted"] == []
    feedback.add(r2, "bad_citation", "d:1", db_path=db)
    feedback.add(r2, "not_useful", db_path=db)
    out = fr.build(db)
    assert out["demoted"] == ["d:1"] and fr.load_demoted(db) == {"d:1"} and out["items"]["not_useful"] == 1
    flagged = next(i for i in fr.items(db) if i["kind"] == "flagged_citation")
    assert flagged["responses"] == 2 and "about roads, not contracts" in flagged["comments"]
    assert flagged["questions"] == ["Why were contracts terminated?", "Why were bids cancelled?"]


def test_no_feedback_file_means_nothing_to_review(tmp_path):
    assert fr.load_demoted(tmp_path / "none.duckdb") == set() and fr.items(tmp_path / "none.duckdb") == []
