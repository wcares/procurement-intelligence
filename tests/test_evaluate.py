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


def _rows():
    q = {"id": "q01", "question": "Why?", "answerable": True}
    m = {"bm25_p5": 0.6, "hybrid_p5": 0.8, "bm25_r10": 0.5, "hybrid_r10": 0.7, "gate_prec": 0.8, "gate_n": 5}
    return [(q, 4, m, "decision", [])], {k: [v] for k, v in m.items()}


def test_report_without_answers_shows_last_measured_answers_and_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "HISTORY", tmp_path / "history.jsonl")
    E.record({"time": "2026-10-25 02:04 UTC", "hybrid_p5": 0.77, "answered": 15, "answerable": 15,
              "supported_sentences": 53, "sentences": 55, "refused_traps": 5, "traps": 5, "median_seconds": 23.3})
    rows, totals = _rows()
    h = E._headline(rows, totals, [], 232)
    fb = {"responses": 3, "ratings": [("ask", "bad_citation", 1), ("ask", "useful", 2)], "flagged_citations": [("40111937:111", 1)]}
    text = E._report(rows, totals, [], 232, h, E._history()[-1], fb)
    assert "| Hybrid precision@5 | 0.80 | 0.77 |" in text          # now vs previous run
    assert "figures from 2026-10-25 02:04 UTC" in text and "53/55" in text  # answers not re-run: dated, not dropped
    assert "| ask | 2 | 0 | 1 |" in text and "`40111937:111` flagged 1×" in text


def test_report_with_no_history_and_no_feedback(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "HISTORY", tmp_path / "history.jsonl")
    rows, totals = _rows()
    text = E._report(rows, totals, [], 10, E._headline(rows, totals, [], 10), None, {"responses": 0, "ratings": [], "flagged_citations": []})
    assert "Not evaluated yet" in text and "No responses logged yet." in text and "| Hybrid precision@5 | 0.80 | – |" in text
