import pytest

from procintel.ingestion import problem_tag as pt


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


def test_a_kind_reply_that_runs_on_keeps_the_problem_with_unknown_kind(monkeypatch):
    calls = iter(["yes"])

    def complete(system, user, max_tokens):
        try:
            return next(calls)
        except StopIteration:
            raise RuntimeError("model output hit max_tokens=20 before finishing")
    monkeypatch.setattr(pt.llm, "complete", complete)
    assert pt.classify("x") == (True, None)
