from procintel import answer
from procintel.retrieve import Hit


def hit(i, text):
    return Hit(chunk_id=f"d:{i}", doc_id="d", title="T", doc_type="ICR", url="u", section="Lessons", para=str(i),
               kind="text", text=text, project_id="P1", project_name="Roads", country_code="KE", score=1.0)


HITS = [
    hit(1, "Two civil works contracts were terminated because the contractor abandoned the site. Payments were late."),
    hit(2, "Consultant selection took eleven months because the terms of reference were revised twice."),
]


def test_question_words_are_not_evidence():
    assert answer.supporting("why were what", HITS) == []
    assert [h.chunk_id for h in answer.supporting("why were contracts terminated", HITS)] == ["d:1"]


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
    out = answer.generative("why were contracts terminated", HITS)
    assert out == [{"text": "Contracts were terminated after the contractor abandoned the site.", "citations": [0]}]


def test_unparseable_model_output_returns_none(monkeypatch):
    monkeypatch.setattr(answer.llm, "complete", lambda system, user: "I think the contracts failed.")
    assert answer.generative("why were contracts terminated", HITS) is None


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
    from procintel import llm
    monkeypatch.setenv("PROCINTEL_LLM_MODEL", "openai/x")
    cut = types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason="length", message=types.SimpleNamespace(content='{"sente'))])
    monkeypatch.setattr(litellm, "completion", lambda **kw: cut)
    import pytest
    with pytest.raises(RuntimeError, match="max_tokens"):
        llm.complete("s", "u")
