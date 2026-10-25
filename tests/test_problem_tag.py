import pytest

from procintel import problem_tag as pt


def replies(monkeypatch, *answers):
    it = iter(answers)
    monkeypatch.setattr(pt.llm, "complete", lambda system, user, max_tokens: next(it))


def test_no_problem_stops_after_the_first_question(monkeypatch):
    replies(monkeypatch, "No.")
    assert pt.classify("Indicator table") == (False, None)


def test_kind_is_read_from_the_second_reply_and_unknown_kinds_become_other(monkeypatch):
    replies(monkeypatch, "Yes", "Land acquisition or resettlement.")
    assert pt.classify("x") == (True, "land acquisition or resettlement")
    replies(monkeypatch, "yes", "staff turnover")
    assert pt.classify("x") == (True, "another kind of problem")


def test_unusable_first_reply_raises(monkeypatch):
    replies(monkeypatch, "Possibly")
    with pytest.raises(RuntimeError):
        pt.classify("x")
