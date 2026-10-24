"""Cited answers to free-text questions over the ICR chunks (the `/ask` endpoint).

Every answer sentence carries citations into the returned passages, and a question the passages do not
support returns `unsupported: true` instead of a guess. Two modes:

  extractive (no LLM configured)  each sentence is the best-matching sentence of a passage, quoted verbatim;
  generative (procintel.llm)      the model writes sentences as JSON with passage numbers; any sentence
                                  without a valid citation, or sharing too few words with the passage it
                                  cites, is dropped. Unparseable output falls back to extractive.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone

import Stemmer
from bm25s.stopwords import STOPWORDS_EN

from procintel import embed, llm
from procintel.retrieve import Hit, Retriever

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
GROUNDING_MIN = 0.3  # share of a generated sentence's content stems that must appear in the cited passage


def terms(text: str) -> set[str]:
    return set(_STEM.stemWords([w for w in re.findall(r"[a-z][a-z-]{2,}", text.lower()) if w not in _STOP]))


def meta(caveats: list[str]) -> dict:
    return {"source": "live", "generatedAt": datetime.now(timezone.utc).isoformat(), "caveats": caveats}


def citation(h: Hit) -> dict:
    section = f"{h.section} ¶{h.para}" if h.para else h.section
    return {"id": h.chunk_id, "docId": h.doc_id, "docType": h.doc_type, "title": h.title, "section": section,
            "quote": h.text, "url": h.url, "projectId": h.project_id, "projectName": h.project_name,
            "countryCode": h.country_code}


def supporting(question: str, hits: list[Hit]) -> list[Hit]:
    """Hits sharing enough of the question's content terms to count as evidence."""
    q = terms(question)
    need = min(2, len(q))
    if need == 0:
        return []
    return [h for h in hits if len(q & terms(h.text)) >= need][:MAX_PASSAGES]


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


def extractive(question: str, hits: list[Hit], weights: dict[str, float] | None = None, n: int = 3) -> list[dict]:
    """The n best sentences across the passages, at most one per passage, each quoted verbatim.

    A sentence must itself share min(2, |question terms|) terms with the question (passage-level overlap is
    not enough), start like a sentence, and not merely point to another section. Rare terms weigh more."""
    q = terms(question)
    need = min(2, len(q))
    w = weights or {}
    best: dict[int, tuple[float, str]] = {}
    for i, h in enumerate(hits):
        for sent in _SENT.split(h.text):
            sent = sent.strip()
            shared = q & terms(sent)
            starts_ok = sent[0].isupper() or sent[0].isdigit()
            if len(shared) < need or len(sent) < 40 or not starts_ok or _POINTER.search(sent):
                continue
            score = sum(w.get(t, 1.0) for t in shared)
            if score > best.get(i, (0.0, ""))[0]:
                best[i] = (score, sent)
    top = sorted(best.items(), key=lambda kv: -kv[1][0])[:n]
    return [{"text": sent, "citations": [i]} for i, (_, sent) in top]


_SYSTEM = """You answer questions for procurement planners using ONLY the numbered evaluation passages given.
Rules:
- Every sentence must be supported by the passages it cites. Do not add facts, numbers or advice that are not in them.
- Reply with JSON only: {"sentences": [{"text": "...", "citations": [1, 2]}]}
- If the passages do not answer the question, reply {"sentences": []}.
- At most 4 sentences."""


def generative(question: str, hits: list[Hit]) -> list[dict] | None:
    """Model-written sentences that survive validation; None when the output is unusable."""
    numbered = "\n\n".join(f"[{i + 1}] ({h.project_id}, {h.section}) {h.text}" for i, h in enumerate(hits))
    raw = llm.complete(_SYSTEM, f"Passages:\n{numbered}\n\nQuestion: {question}")
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        sentences = json.loads(m.group(0))["sentences"] if m else None
    except (json.JSONDecodeError, KeyError, TypeError):
        sentences = None
    if not isinstance(sentences, list):
        return None
    out = []
    for s in sentences:
        if not isinstance(s, dict) or not isinstance(s.get("text"), str):
            continue
        cites = sorted({c - 1 for c in s.get("citations") or [] if isinstance(c, int) and 1 <= c <= len(hits)})
        st = terms(s["text"])
        cited = set().union(*(terms(hits[c].text) for c in cites)) if cites else set()
        if cites and st and len(st & cited) / len(st) >= GROUNDING_MIN:
            out.append({"text": s["text"].strip(), "citations": cites})
    return out


def retrieval_note(hits: list[Hit]) -> str:
    vias = {v for h in hits for v in h.via.split("+")}
    if "vector" in vias:
        return f"Passages found by keyword (BM25) and semantic ({embed.model_name()}) search, merged by rank."
    return "Passages found by keyword search (BM25)."


def ask(retriever: Retriever, question: str, country: str | None = None, proc_group: str | None = None) -> dict:
    hits = supporting(question, retriever.search(question, k=12, country=country, proc_group=proc_group))
    caveats = []
    if not hits:
        return {"answer": [], "citations": [], "unsupported": True,
                "meta": meta(["No evaluation passage shares enough terms with the question to count as evidence."])}
    answer = None
    if llm.available():
        try:
            answer = generative(question, hits)
        except Exception as e:  # model server down, timeout, auth: answer extractively rather than fail
            caveats.append(f"Language model call failed ({type(e).__name__}); showing quoted sentences instead.")
        else:
            if answer is None:
                caveats.append("Language model output could not be parsed; showing quoted sentences instead.")
            elif not answer:
                caveats.append(f"{llm.model_name()} found no answer to this question in the retrieved passages.")
            else:
                caveats.append(f"Sentences written by {llm.model_name()} from the cited passages; each was checked "
                               "for a valid citation and word overlap with it, which does not prove every detail.")
    if answer is None:
        answer = extractive(question, hits, idf(retriever))
        caveats.append("Each sentence is quoted verbatim from the cited evaluation passage.")
    caveats.append(retrieval_note(hits))
    used = sorted({c for s in answer for c in s["citations"]})
    remap = {old: new for new, old in enumerate(used)}
    return {
        "answer": [{"text": s["text"], "citations": [remap[c] for c in s["citations"]]} for s in answer],
        "citations": [citation(hits[i]) for i in used],
        "unsupported": not answer,
        "meta": meta(caveats),
    }
