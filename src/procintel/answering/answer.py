"""Cited answers to free-text questions over the ICR chunks (the `/ask` endpoint).

Every answer sentence carries citations into the returned passages, and a question the passages do not
support returns `unsupported: true` instead of a guess. Two modes:

  extractive (no LLM configured)  each sentence is the best-matching sentence of a passage, quoted verbatim;
  generative (procintel.core.llm)      the model writes sentences as JSON with passage numbers; any sentence
                                  without a valid citation, or not supported by the passage it cites, is
                                  dropped. Unparseable output falls back to extractive.

Three checks use a decision model (procintel.core.decide) when one is configured, and word overlap otherwise or when
the decision server fails: which retrieved passages count as evidence, which generated sentences their cited
passages support, and which sentence of a passage best answers the question.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone

import Stemmer
from bm25s.stopwords import STOPWORDS_EN

from procintel.answering.retrieve import Hit, Retriever
from procintel.core import decide, embed, llm, prompts

_STEM = Stemmer.Stemmer("english")
# question words carry no evidence: "why were contracts cancelled" should need "contract" + "cancel"
_STOP = set(STOPWORDS_EN) | set(
    "what why how which who whom when where were was did does do has have had been can could would should "
    "may might any all more most than also about from into over under after before during project projects "
    "cause caused causes reason reasons happen happened".split())
# no split after abbreviations common in ICRs ("Rs. 40 crore", "US$ 2 m.", "No. 3", "e.g. the")
_ABBREV = r"(?<!\bRs\.)(?<!\bNo\.)(?<!\bUS\.)(?<!\bvs\.)(?<!\bMr\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\be\.g\.)(?<!\bi\.e\.)"
_SENT = re.compile(r"(?<=[.;])" + _ABBREV + r"\s+(?=[A-Z0-9])")
MAX_PASSAGES = 5
SEARCH_K = 12  # passages retrieved per question before the evidence check
MIN_EVIDENCE = 3  # fewer evidence passages than this triggers a second search with reformulated queries (needs an LLM)
GROUNDING_MIN = 0.3  # word-overlap fallback: share of a sentence's content stems that must appear in the cited passage
DECIDE_MIN = 0.5  # decision-model probability needed for "relevant" and "supported"
# 1: the answer LLM picks the evidence passages in one call; 0: the decision model judges each passage. Measured on the
# 20 evaluation questions plus a paraphrase (2026-10-25): precision vs the judged labels 0.95 vs 0.82 (recall 0.91 vs
# 0.86), vs hand labels 0.89 vs 0.62; traps with any passage kept 0 of 5 vs 2 of 5; the paraphrase "Why did firms stop
# showing up to bid?" kept 3 passages vs 1. Cost: about 14 s per question vs 0.4 s.
LLM_GATE = 1
# 1: before the first search the answer LLM rephrases the question in the reports' vocabulary and the searches are
# merged. If none of the evidence comes from the question's own search, that search is judged too and the question is
# refused when it has no evidence there (otherwise both are used). Measured on the 10 everyday-wording evaluation
# questions and 10 others (2026-10-25): relevant passages among the 12 the gate sees 45 -> 59 and 66 -> 73. Without the
# own-search check the "high-speed rail" trap got through again (2 of 2 runs); refusing outright whenever no evidence
# came from the own search lost 2 answerable questions (misprocurement, PPP). Cost: about 2.3 s per question.
VOCAB_STEP = 1


def terms(text: str) -> set[str]:
    return set(_STEM.stemWords([w for w in re.findall(r"[a-z][a-z-]{2,}", text.lower()) if w not in _STOP]))


def meta(caveats: list[str]) -> dict:
    return {"source": "live", "generatedAt": datetime.now(timezone.utc).isoformat(), "caveats": caveats}


def citation(h: Hit) -> dict:
    section = f"{h.section} ¶{h.para}" if h.para else h.section
    return {"id": h.chunk_id, "docId": h.doc_id, "docType": h.doc_type, "title": h.title, "section": section,
            "quote": h.text, "url": h.url, "projectId": h.project_id, "projectName": h.project_name,
            "countryCode": h.country_code}


def llm_gate(question: str, hits: list[Hit]) -> list[Hit]:
    """Hits the answer LLM lists as helping to answer the question, in retrieval order (one call for all hits).
    Raises on a failed call or an unusable reply, so the caller can fall back."""
    if not hits:
        return []
    numbered = "\n\n".join(f"[{i + 1}] {h.text}" for i, h in enumerate(hits))
    raw = llm.complete(prompts.get("evidence_gate"), f"Question: {question}\n\nPassages:\n{numbered}", max_tokens=200)
    picked = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))["relevant"]
    return [hits[i - 1] for i in sorted({int(i) for i in picked if 1 <= int(i) <= len(hits)})]


def supporting(question: str, hits: list[Hit]) -> tuple[list[Hit], str]:
    """(hits that count as evidence, how that was decided: "llm", "decision" or "terms"). With LLM_GATE the answer LLM
    picks the passages; otherwise, or if that call fails, the decision model judges each passage; without it, a passage
    must share min(2, |question terms|) content terms with the question."""
    if LLM_GATE and llm.available():
        try:
            return llm_gate(question, hits)[:MAX_PASSAGES], "llm"
        except Exception:  # model down, timeout or unparseable reply: the decision model judges instead
            pass
    if decide.available():
        try:
            keep = [h for h in hits if decide.yes(f"Question: {question}\nPassage: {h.text}",
                                                  "Does the passage contain information that helps answer the question?") >= DECIDE_MIN]
            return keep[:MAX_PASSAGES], "decision"
        except Exception:  # decision server down: the word-overlap rule still gives a usable evidence set
            pass
    q = terms(question)
    need = min(2, len(q))
    if need == 0:
        return [], "terms"
    return [h for h in hits if len(q & terms(h.text)) >= need][:MAX_PASSAGES], "terms"


_IDF: dict[int, dict[str, float]] = {}


def idf(retriever: Retriever) -> dict[str, float]:
    """Inverse document frequency of each stem over all chunks, computed once per retriever."""
    if id(retriever) not in _IDF:
        df = Counter(t for r in retriever.records for t in terms(r["text"]))
        n = len(retriever.records)
        _IDF[id(retriever)] = {t: math.log(n / c) for t, c in df.items()}
    return _IDF[id(retriever)]


# sentences that only point elsewhere in the report ("discussed in section IV") answer nothing
_POINTER = re.compile(r"\b(?:discussed|described|presented|detailed|see)\b.{0,40}\b(?:section|annex|paragraph|below|above)\b", re.I)


def _candidates(text: str) -> list[str]:
    """Sentences of a passage that could stand as a quote: long enough, starting like a sentence, not a pointer."""
    out = []
    for sent in _SENT.split(text):
        sent = sent.strip()
        if len(sent) >= 40 and (sent[0].isupper() or sent[0].isdigit()) and not _POINTER.search(sent):
            out.append(sent)
    return out


def extractive(question: str, hits: list[Hit], weights: dict[str, float] | None = None, n: int = 3,
               use_decide: bool = False) -> list[dict]:
    """The n best sentences across the passages, at most one per passage, each quoted verbatim.

    With use_decide, the decision model scores whether each candidate sentence answers the question (>= DECIDE_MIN).
    Otherwise a sentence must itself share min(2, |question terms|) terms with the question (passage-level overlap
    is not enough), and rare terms weigh more."""
    q = terms(question)
    need = min(2, len(q))
    w = weights or {}
    best: dict[int, tuple[float, str]] = {}
    for i, h in enumerate(hits):
        for sent in _candidates(h.text):
            if use_decide:
                score = decide.yes(f"Question: {question}\nSentence: {sent}", "Does the sentence answer the question?")
                if score < DECIDE_MIN:
                    continue
            else:
                shared = q & terms(sent)
                if len(shared) < need:
                    continue
                score = sum(w.get(t, 1.0) for t in shared)
            if score > best.get(i, (0.0, ""))[0]:
                best[i] = (score, sent)
    top = sorted(best.items(), key=lambda kv: -kv[1][0])[:n]
    return [{"text": sent, "citations": [i]} for i, (_, sent) in top]


def _supported(sentence: str, cited: list[Hit], use_decide: bool) -> bool:
    if use_decide:
        evidence = "\n\n".join(h.text for h in cited)
        return decide.yes(f"Passage: {evidence}\nClaim: {sentence}", "Is the claim supported by the passage?") >= DECIDE_MIN
    st = terms(sentence)
    cited_terms = set().union(*(terms(h.text) for h in cited))
    return bool(st) and len(st & cited_terms) / len(st) >= GROUNDING_MIN


def generative(question: str, hits: list[Hit], use_decide: bool = False) -> tuple[list[dict] | None, int]:
    """(model-written sentences that survive validation, number dropped as unsupported); None when the output
    is unusable. A sentence needs a valid citation and must be supported by what it cites."""
    numbered = "\n\n".join(f"[{i + 1}] ({h.project_id}, {h.section}) {h.text}" for i, h in enumerate(hits))
    raw = llm.complete(prompts.get("answer"), f"Passages:\n{numbered}\n\nQuestion: {question}")
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        sentences = json.loads(m.group(0))["sentences"] if m else None
    except (json.JSONDecodeError, KeyError, TypeError):
        sentences = None
    if not isinstance(sentences, list):
        return None, 0
    out, dropped = [], 0
    for s in sentences:
        if not isinstance(s, dict) or not isinstance(s.get("text"), str):
            continue
        cites = sorted({c - 1 for c in s.get("citations") or [] if isinstance(c, int) and 1 <= c <= len(hits)})
        if cites and _supported(s["text"], [hits[c] for c in cites], use_decide):
            out.append({"text": s["text"].strip(), "citations": cites})
        else:
            dropped += 1
    return out, dropped


def conflict_notes(retriever: Retriever, cited: list[Hit]) -> list[str]:
    """Caveats for cited reports whose completion rating disagrees with the last supervision rating, or whose procurement
    rating is lower than a satisfactory overall rating."""
    notes, seen = [], set()
    for h in cited:
        note = getattr(retriever, "rating_conflicts", {}).get(h.doc_id)
        if note and h.doc_id not in seen:
            seen.add(h.doc_id)
            notes.append(f"Conflicting evidence for {h.project_id} ({h.project_name}): {note}")
    seen = set()
    for h in cited:
        note = getattr(retriever, "procurement_conflicts", {}).get(h.doc_id)
        if note and h.doc_id not in seen:
            seen.add(h.doc_id)
            notes.append(f"Procurement weaker than the overall rating for {h.project_id} ({h.project_name}): {note}")
    return notes


def retrieval_note(hits: list[Hit]) -> str:
    vias = {v for h in hits for v in h.via.split("+")}
    if "vector" in vias:
        return f"Passages found by keyword (BM25) and semantic ({embed.model_name()}) search, merged by rank."
    return "Passages found by keyword search (BM25)."


def reformulate(question: str) -> list[str]:
    """Up to 3 search queries in the reports' vocabulary; [] if the reply is unusable."""
    raw = llm.complete(prompts.get("rephrase"), question, max_tokens=150)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        qs = json.loads(m.group(0))["queries"] if m else []
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    return [q.strip() for q in qs if isinstance(q, str) and q.strip()][:3]


def fuse(rankings: list[list[Hit]], k: int) -> list[Hit]:
    """Rankings merged by reciprocal rank fusion, each passage once."""
    fused: dict[str, float] = {}
    by_id: dict[str, Hit] = {}
    for ranking in rankings:
        for rank, h in enumerate(ranking):
            fused[h.chunk_id] = fused.get(h.chunk_id, 0.0) + 1.0 / (60 + rank + 1)
            by_id.setdefault(h.chunk_id, h)
    return [by_id[c] for c in sorted(fused, key=fused.get, reverse=True)][:k]


def search_multi(retriever: Retriever, queries: list[str], k: int, country: str | None, proc_group: str | None) -> list[Hit]:
    """Hits of several queries merged by reciprocal rank fusion, each passage once."""
    return fuse([retriever.search(q, k=k, country=country, proc_group=proc_group) for q in queries], k)


def ask(retriever: Retriever, question: str, country: str | None = None, proc_group: str | None = None) -> dict:
    own = retriever.search(question, k=SEARCH_K, country=country, proc_group=proc_group)
    rephrased = None
    if VOCAB_STEP and llm.available():
        try:
            rephrased = reformulate(question)
        except Exception:  # model down: search with the question only
            rephrased = None
    if rephrased:
        hits, judged_by = supporting(question, fuse([own] + [retriever.search(q, k=SEARCH_K, country=country,
                                                                        proc_group=proc_group) for q in rephrased], SEARCH_K))
        own_ids = {h.chunk_id for h in own}
        if judged_by == "llm" and not any(h.chunk_id in own_ids for h in hits):
            # evidence only through the rephrasing: judge the question's own search; nothing there means the question is
            # out of scope and the rephrased evidence is a look-alike (the "HSIP" case); otherwise use both
            try:
                confirmed = llm_gate(question, own)
            except Exception:
                confirmed = []
            hits = (hits + [h for h in confirmed if h not in hits])[:MAX_PASSAGES] if confirmed else []
    else:
        hits, judged_by = supporting(question, own)
    second_search = rephrased or None
    # step 2: too little evidence; search again with the question rephrased in the reports' vocabulary. Not when the
    # answer LLM found no evidence at all: measured on the 100 evaluation questions plus a paraphrase, every answerable
    # question kept at least 1 passage on the first pass and 18 of 20 unanswerable ones kept none, while the second
    # search let the "high-speed rail" trap through on a passage about an unrelated "HSIP" project.
    if not rephrased and len(hits) < MIN_EVIDENCE and llm.available() and (hits or judged_by != "llm"):
        try:
            queries = reformulate(question)
        except Exception:  # model down: keep the first search
            queries = []
        if queries:
            more, how2 = supporting(question, search_multi(retriever, [question] + queries, SEARCH_K, country, proc_group))
            if len(more) > len(hits):
                hits, judged_by, second_search = more, how2, queries
    use_decide = judged_by in ("llm", "decision") and decide.available()  # sentences are checked by the decision model
    checker = f"the decision model {decide.api_base()}" if use_decide else "word overlap"
    caveats = [] if judged_by != "terms" or not decide.available() else [
        "Decision model unavailable; evidence and support were checked by word overlap instead."]
    judge = {"llm": llm.model_name(), "decision": "The decision model"}.get(judged_by)
    if not hits:
        why = (f"{judge} judged none of the retrieved passages relevant to the question." if judge
               else "No evaluation passage shares enough terms with the question to count as evidence.")
        return {"answer": [], "citations": [], "unsupported": True, "meta": meta(caveats + [why])}
    answer = None
    if llm.available():
        try:
            answer, dropped = generative(question, hits, use_decide)
        except Exception as e:  # model server down, timeout, auth: answer extractively rather than fail
            caveats.append(f"Language model call failed ({type(e).__name__}); showing quoted sentences instead.")
        else:
            if answer is None:
                caveats.append("Language model output could not be parsed; showing quoted sentences instead.")
            elif not answer:
                caveats.append(f"{llm.model_name()} found no supported answer to this question in the retrieved passages.")
            else:
                caveats.append(f"Sentences written by {llm.model_name()} from the cited passages; each was checked "
                               f"against the passages it cites by {checker}, which does not prove every detail.")
            if dropped:
                caveats.append(f"{dropped} generated sentence(s) were dropped because their cited passages did not support them.")
    if answer is None:
        try:
            answer = extractive(question, hits, idf(retriever), use_decide=use_decide)
        except Exception:  # decision server failed mid-request: pick quotes by word overlap
            answer = extractive(question, hits, idf(retriever))
            caveats.append("Decision model failed while choosing quotes; quotes were chosen by word overlap.")
        caveats.append("Each sentence is quoted verbatim from the cited evaluation passage." if answer else
                       "Related passages were found, but no sentence in them answers the question directly.")
    caveats.append(retrieval_note(hits) + {"llm": f" Relevance judged by {llm.model_name()}.",
                                           "decision": " Relevance judged by the decision model."}.get(judged_by, ""))
    if second_search:
        caveats.append(("The question was also searched as: " if rephrased else
                        "The first search found little evidence, so the question was searched again as: ")
                       + "; ".join(f"'{q}'" for q in second_search) + ".")
    used = sorted({c for s in answer for c in s["citations"]})
    caveats += conflict_notes(retriever, [hits[i] for i in used])
    remap = {old: new for new, old in enumerate(used)}
    return {
        "answer": [{"text": s["text"], "citations": [remap[c] for c in s["citations"]]} for s in answer],
        "citations": [citation(hits[i]) for i in used],
        "unsupported": not answer,
        "meta": meta(caveats),
    }
