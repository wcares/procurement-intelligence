from procintel import evaluate as E


def test_precision_and_recall_against_the_judged_relevant_set():
    rel = {"a", "b", "c", "d"}
    assert E._prec(["a", "x", "b", "y"], rel) == 0.5
    assert E._rec(["a", "x", "b"], rel) == 0.5          # 2 of the 4 relevant passages found
    assert E._prec([], rel) is None                      # nothing kept: no precision rather than 0
    assert E._rec(["a"], set()) is None                  # no relevant passage known: recall undefined


def test_search_restores_vectors_after_a_keyword_only_query():
    class R:
        vectors = "V"
        seen = None

        def search(self, q, k):
            R.seen = self.vectors
            return []
    r = R()
    E._search(r, "q", 5, hybrid=False)
    assert R.seen is None and r.vectors == "V"           # keyword-only for the call, hybrid again afterwards


def test_judge_rejects_anything_but_yes_or_no(monkeypatch):
    import pytest
    monkeypatch.setattr(E.llm, "complete", lambda system, user, max_tokens: "Maybe, it depends.")
    with pytest.raises(RuntimeError, match="expected yes or no"):
        E._yes("s", "u")
