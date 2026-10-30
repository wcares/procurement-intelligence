from procintel.answering import answer
from procintel.answering.retrieve import Hit


def hit(i, text):
    return Hit(chunk_id=f"d:{i}", doc_id="d", title="T", doc_type="ICR", url="u", section="Lessons", para=str(i),
               kind="text", text=text, project_id="P1", project_name="Roads", country_code="KE", score=1.0)


HITS = [
    hit(1, "Two civil works contracts were terminated because the contractor abandoned the site. Payments were late."),
    hit(2, "Consultant selection took eleven months because the terms of reference were revised twice."),
]


def fake_generative(result):
    """Stands in for answer.generative_events: no sentences streamed, the given (sentences, dropped) as the result."""
    def events(q, hits, use_decide=False, streaming=True):
        return result
        yield
    return events


def test_question_words_are_not_evidence(monkeypatch):
    for v in ("PROCINTEL_LLM_MODEL", "PROCINTEL_DECIDE_API_BASE"):  # word-overlap rule only
        monkeypatch.delenv(v, raising=False)
    assert answer.supporting("why were what", HITS) == ([], "terms")
    hits, how = answer.supporting("why were contracts terminated", HITS)
    assert [h.chunk_id for h in hits] == ["d:1"] and how == "terms"


def test_extractive_quotes_a_source_sentence_verbatim():
    out = answer.extractive("contracts terminated contractor", HITS[:1])
    assert out == [{"text": "Two civil works contracts were terminated because the contractor abandoned the site.", "citations": [0]}]


def test_generated_sentences_without_valid_grounded_citations_are_dropped(monkeypatch):
    reply = """Here you go: {"sentences": [
        {"text": "Contracts were terminated after the contractor abandoned the site.", "citations": [1]},
        {"text": "Contracts were terminated after the contractor abandoned the site.", "citations": [7]},
        {"text": "The ministry should adopt e-procurement nationwide by 2030.", "citations": [1]},
        {"text": "Selection of the consultant was slow.", "citations": []}
    ]}"""
    monkeypatch.setattr(answer.llm, "complete", lambda system, user: reply)
    out, dropped = answer.generative("why were contracts terminated", HITS)
    assert dropped == 3
    assert out == [{"text": "Contracts were terminated after the contractor abandoned the site.", "citations": [0]}]


def test_unparseable_model_output_returns_none(monkeypatch):
    monkeypatch.setattr(answer.llm, "complete", lambda system, user: "I think the contracts failed.")
    assert answer.generative("why were contracts terminated", HITS) == (None, 0)


def test_extractive_skips_pointers_fragments_and_weak_sentences():
    hits = [hit(3, "proved effective in strengthening procurement capacity of the agency. "
                   "These procurement capacity issues are further discussed in the Lessons Learned section. "
                   "Procurement capacity was built through hands-on training of the agency staff in the first year.")]
    assert [s["text"] for s in answer.extractive("procurement capacity lessons", hits)] == [
        "Procurement capacity was built through hands-on training of the agency staff in the first year."]


def test_extractive_prefers_rare_terms_and_one_sentence_per_passage():
    hits = [hit(4, "Civil works contracts were signed for twelve roads in the first year of the project. "
                   "Civil works were delayed because the contracts waited for land acquisition.")]
    out = answer.extractive("delays in civil works contracts", hits, {"delay": 5.0})
    assert out == [{"text": "Civil works were delayed because the contracts waited for land acquisition.", "citations": [0]}]


def test_retrieval_note_names_the_method_actually_used(monkeypatch):
    monkeypatch.setenv("PROCINTEL_EMBED_MODEL", "openai/embeddinggemma-2")
    vec = hit(5, "x"); vec.via = "bm25+vector"
    assert "semantic (openai/embeddinggemma-2)" in answer.retrieval_note([HITS[0], vec])
    assert answer.retrieval_note(HITS) == "Passages found by keyword search (BM25)."


def test_cut_model_output_is_an_error_not_an_answer(monkeypatch):
    import types, litellm
    from procintel.core import llm
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/x")
    cut = types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason="length", message=types.SimpleNamespace(content='{"sente'))])
    monkeypatch.setattr(litellm, "completion", lambda **kw: cut)
    import pytest
    with pytest.raises(RuntimeError, match="max_tokens"):
        llm.complete("s", "u")


def fake_decider(monkeypatch, rule):
    """Route decide.yes to rule(state) -> probability, and mark the decision model as configured."""
    from procintel.core import decide
    monkeypatch.setenv("PROCINTEL_DECIDE_API_BASE", "http://fake")
    monkeypatch.delenv("PROCINTEL_LLM_MODEL", raising=False)  # no answer LLM: the decision model is the gate
    monkeypatch.setattr(decide, "yes", lambda state, question, **kw: rule(state))


def test_decision_model_selects_evidence_without_shared_words(monkeypatch):
    # "firms stopped bidding" shares no content word with the consultant passage; the decision model decides
    fake_decider(monkeypatch, lambda state: 0.9 if "eleven months" in state else 0.1)
    hits, how = answer.supporting("why did firms stop bidding", HITS)
    assert how == "decision" and [h.chunk_id for h in hits] == ["d:2"]


def test_decision_model_drops_unsupported_generated_sentences(monkeypatch):
    fake_decider(monkeypatch, lambda state: 0.95 if "abandoned" in state.split("Claim:")[1] else 0.05)
    reply = '{"sentences": [{"text": "The contractor abandoned the site.", "citations": [1]}, ' \
            '{"text": "Contracts were terminated after a corruption probe.", "citations": [1]}]}'
    monkeypatch.setattr(answer.llm, "complete", lambda system, user: reply)
    out, dropped = answer.generative("why were contracts terminated", HITS, use_decide=True)
    assert [s["text"] for s in out] == ["The contractor abandoned the site."] and dropped == 1


def test_decision_server_failure_falls_back_to_word_overlap(monkeypatch):
    from procintel.core import decide
    monkeypatch.setenv("PROCINTEL_DECIDE_API_BASE", "http://fake")

    def down(*a, **kw):
        raise ConnectionError("decision server not running")
    monkeypatch.setattr(decide, "yes", down)
    monkeypatch.delenv("PROCINTEL_LLM_MODEL", raising=False)
    hits, how = answer.supporting("why were contracts terminated", HITS)
    assert how == "terms" and [h.chunk_id for h in hits] == ["d:1"]


def test_second_search_runs_only_when_evidence_is_thin_and_keeps_the_larger_set(monkeypatch):
    monkeypatch.setattr(answer, "VOCAB_STEP", 0)                      # the older thin-evidence path
    from procintel.answering.retrieve import Hit as H
    calls = []

    class R:
        records = []

        def search(self, q, k, country=None, proc_group=None):
            calls.append(q)
            return HITS if "contractor" in q else []          # the original wording finds nothing
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/fake")
    monkeypatch.setattr(answer, "reformulate", lambda q: ["contractor abandoned terminated contracts"])
    monkeypatch.setattr(answer, "supporting", lambda q, hits: (hits[:1], "terms"))
    monkeypatch.setattr(answer, "generative_events", fake_generative(([{"text": "Contracts were terminated.", "citations": [0]}], 0)))
    out = answer.ask(R(), "why did firms stop showing up")
    assert calls[0] == "why did firms stop showing up" and "contractor abandoned terminated contracts" in calls
    assert not out["unsupported"] and any("searched again" in c for c in out["meta"]["caveats"])


def test_no_second_search_when_the_first_finds_enough(monkeypatch):
    monkeypatch.setattr(answer, "VOCAB_STEP", 0)                      # the older thin-evidence path
    class R:
        records = []

        def search(self, q, k, country=None, proc_group=None):
            return HITS
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/fake")
    monkeypatch.setattr(answer, "reformulate", lambda q: (_ for _ in ()).throw(AssertionError("should not reformulate")))
    monkeypatch.setattr(answer, "supporting", lambda q, hits: (hits * 2, "terms"))     # 4 >= MIN_EVIDENCE
    monkeypatch.setattr(answer, "generative_events", fake_generative(([{"text": "x y z.", "citations": [0]}], 0)))
    answer.ask(R(), "why were contracts terminated")


def test_answer_llm_picks_evidence_in_one_call_and_falls_back_to_the_decision_model(monkeypatch):
    calls = []
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/fake")
    monkeypatch.setattr(answer.llm, "complete", lambda system, user, max_tokens: calls.append(user) or '{"relevant": [2, 9]}')
    hits, how = answer.supporting("why did firms stop bidding", HITS)
    assert how == "llm" and [h.chunk_id for h in hits] == ["d:2"] and len(calls) == 1   # out-of-range 9 ignored
    monkeypatch.setattr(answer.llm, "complete", lambda *a, **kw: '{"relevant": []}')
    assert answer.supporting("Who won the 2018 FIFA World Cup?", HITS) == ([], "llm")  # nothing helps: no evidence
    monkeypatch.setattr(answer.llm, "complete", lambda *a, **kw: "Passage 2 looks relevant.")  # unusable reply
    fake_decider(monkeypatch, lambda state: 0.9 if "eleven months" in state else 0.1)
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/fake")
    assert answer.supporting("why did firms stop bidding", HITS)[1] == "decision"
    monkeypatch.setattr(answer, "LLM_GATE", 0)                                               # switched off on /config
    monkeypatch.setattr(answer.llm, "complete", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("not called")))
    assert answer.supporting("why did firms stop bidding", HITS)[1] == "decision"


def test_no_second_search_when_the_answer_llm_found_no_evidence(monkeypatch):
    monkeypatch.setattr(answer, "VOCAB_STEP", 0)                      # the older thin-evidence path
    class R:
        def search(self, q, k, country=None, proc_group=None):
            return HITS
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/fake")
    monkeypatch.setattr(answer, "reformulate", lambda q: (_ for _ in ()).throw(AssertionError("should not reformulate")))
    monkeypatch.setattr(answer, "supporting", lambda q, hits: ([], "llm"))
    out = answer.ask(R(), "What procurement problems affected the high-speed rail lines?")
    assert out["unsupported"] and "judged none of the retrieved passages relevant" in out["meta"]["caveats"][-1]


def test_vocabulary_step_searches_rephrasings_and_needs_evidence_from_the_own_search(monkeypatch):
    from procintel.answering.retrieve import Hit as H
    own = HITS[:1]
    lookalike = H(chunk_id="x:9", doc_id="x", title="T", doc_type="ICR", url="u", section="Lessons", para="9", kind="text",
                  text="HSIP metering equipment certification delays.", project_id="P9", project_name="HSIP",
                  country_code="KE", score=1.0)

    class R:
        records = []

        def search(self, q, k, country=None, proc_group=None):
            return own if q == "the question" else [lookalike]
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/fake")
    monkeypatch.setattr(answer, "reformulate", lambda q: ["report words"])
    monkeypatch.setattr(answer, "generative_events", fake_generative(([{"text": "x y z.", "citations": [0]}], 0)))
    monkeypatch.setattr(answer, "supporting", lambda q, hits: ([h for h in hits if h.chunk_id == "x:9"], "llm"))
    monkeypatch.setattr(answer, "llm_gate", lambda q, hits: [])
    assert answer.ask(R(), "the question")["unsupported"]           # own search has no evidence: the look-alike is not kept
    monkeypatch.setattr(answer, "llm_gate", lambda q, hits: [h for h in hits if h.chunk_id == "d:1"])
    seen_cites = []
    def record(q, hits, use_decide=False, streaming=True):
        seen_cites.append([h.chunk_id for h in hits])
        return ([{"text": "x y z.", "citations": [0]}], 0)
        yield
    monkeypatch.setattr(answer, "generative_events", record)
    assert not answer.ask(R(), "the question")["unsupported"] and seen_cites[-1] == ["x:9", "d:1"]  # in scope: both used
    monkeypatch.setattr(answer, "generative_events", fake_generative(([{"text": "x y z.", "citations": [0]}], 0)))
    seen = []
    monkeypatch.setattr(answer, "supporting", lambda q, hits: seen.append([h.chunk_id for h in hits]) or (hits, "llm"))
    out = answer.ask(R(), "the question")
    assert set(seen[0]) == {"d:1", "x:9"} and not out["unsupported"]  # both searches go to the gate
    assert any("also searched as: 'report words'" in c for c in out["meta"]["caveats"])


REPLY = ('{"sentences": [{"text": "Contracts were terminated after the contractor abandoned the site.", "citations": [1]},'
         ' {"text": "The ministry should adopt e-procurement nationwide by 2030.", "citations": [1]},'
         ' {"text": "Consultant selection took long: \\"revised twice\\" {terms}.", "citations": [2]}]}')


def pieces(text, n=7):
    return [text[i:i + n] for i in range(0, len(text), n)]


def test_objects_are_found_whatever_size_the_pieces_arrive_in():
    for n in (1, 3, 11, 500):
        scan, found = answer._Objects(), []
        for piece in pieces('Sure! ' + REPLY + " done", n):
            found += scan.feed(piece)
        assert len(found) == 3 and found[2].endswith('{terms}.", "citations": [2]}')   # a brace inside a string is text


def test_sentences_are_yielded_as_written_and_the_result_is_the_old_one(monkeypatch):
    monkeypatch.setattr(answer.llm, "stream", lambda system, user: iter(pieces(REPLY)))
    events = answer.generative_events("why were contracts terminated", HITS)
    got = []
    while True:
        try:
            got.append(next(events))
        except StopIteration as done:
            result = done.value
            break
    assert [e["text"] for e in got] == ["Contracts were terminated after the contractor abandoned the site.",
                                         "Consultant selection took long: \"revised twice\" {terms}."]
    monkeypatch.setattr(answer.llm, "complete", lambda system, user: REPLY)
    assert result == answer.generative("why were contracts terminated", HITS)   # streaming changes when, not what
    assert result[1] == 1


def test_ask_events_run_in_order_and_end_with_the_answer(monkeypatch):
    for v in ("PROCINTEL_LLM_MODEL", "PROCINTEL_DECIDE_API_BASE"):
        monkeypatch.delenv(v, raising=False)

    class R:
        records = []

        def search(self, q, k, country=None, proc_group=None):
            return HITS
    kinds = [e["type"] for e in answer.ask_events(R(), "why were contracts terminated")]
    assert kinds[0] == "stage" and kinds[-1] == "done" and kinds.index("passages") < kinds.index("done")
    assert [e["type"] for e in answer.ask_events(R(), "why were what")][-1] == "done"   # no evidence: still ends with an answer


def test_unsupported_question_still_gets_a_plain_reply(monkeypatch):
    class R:
        records = []

        def search(self, q, k, country=None, proc_group=None):
            return HITS
    monkeypatch.setattr(answer, "VOCAB_STEP", 0)
    monkeypatch.setattr(answer, "supporting", lambda q, hits: ([], "terms"))
    out = answer.ask(R(), "Why is Morocco slowest?")
    assert out["unsupported"] and out["answer"] == []                       # the refusal fields are unchanged
    lead = out["fallback"]["answer"][0]
    assert lead["citations"] == [] and "searched the reports" in lead["text"]   # a sentence that says what was tried
