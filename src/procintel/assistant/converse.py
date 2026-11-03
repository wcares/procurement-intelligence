"""A conversational answer in the planning chat: the planner talks freely, and every answer is built from what we hold.

For each message the assistant gets the conversation so far, the plan and its forecast, and the passages the reports
offer for the message (hybrid search, in the plan's country first when one is set). The model (prompt chat_converse)
writes sentences of three kinds, and each is checked before it is shown:
  evidence  about past projects: needs citations, and each sentence is checked against the passages it cites (the same
            check as Ask: the decision model when there is one, else word overlap); an unsupported one is dropped
  plan      about the planner's plan or forecast: every number in it must appear in the plan or the forecast
  data      from the engine's own figures a tool returned (an assessment, a statistic; procintel.assistant.agent):
            every number in it must appear in what the tools returned
  general   brief general advice: kept, and labelled on the page as not coming from the reports
The result has the shape of an Ask answer, so the page shows it with the same citation cards, flags and caveats.
"""
from __future__ import annotations

import json
import re

from procintel.answering import answer
from procintel.answering.retrieve import Hit, Retriever
from procintel.core import decide, llm, prompts

PASSAGES = 6          # passages given to the model
HISTORY = 8           # last messages of the conversation given to it
MESSAGE_CHARS = 1200  # each message cut to this length
KINDS = ("evidence", "plan", "data", "general")
_NUMBER = re.compile(r"\d[\d,.]*")


def _numbers(text: str) -> set[str]:
    return {n.rstrip(".,").replace(",", "") for n in _NUMBER.findall(text)}


def find_passages(retriever: Retriever, message: str, country: str | None) -> list[Hit]:
    """The message's passages: from the plan's country first (when one is set), then from anywhere, merged by rank."""
    rankings = [retriever.search(message, k=PASSAGES, country=country)] if country else []
    rankings.append(retriever.search(message, k=PASSAGES))
    return answer.fuse(rankings, PASSAGES)


def _context(history: list[dict], plan_text: str, results: str, hits: list[Hit]) -> str:
    talk = "\n".join(f"{'Planner' if m['role'] == 'user' else 'Assistant'}: {m['content'][:MESSAGE_CHARS]}"
                     for m in history[-HISTORY:])
    passages = "\n\n".join(f"[{i + 1}] ({h.title}, {h.project_id}, {h.section}) {h.text}" for i, h in enumerate(hits))
    return (f"PLAN:\n{plan_text or '(empty)'}\n\nFORECAST:\n{results or '(none yet)'}\n\nPASSAGES:\n{passages or '(none found)'}"
            f"\n\nCONVERSATION:\n{talk}")


def _parse(raw: str) -> list[dict] | None:
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        out = json.loads(m.group(0))["sentences"] if m else None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    return out if isinstance(out, list) else None


def check(sentences: list[dict], hits: list[Hit], grounding: str, use_decide: bool) -> tuple[list[dict], int]:
    """(the sentences that pass their check, how many were dropped)."""
    kept, dropped = [], 0
    allowed = _numbers(grounding)
    for s in sentences:
        if not isinstance(s, dict) or not isinstance(s.get("text"), str) or not s["text"].strip():
            continue
        kind = s.get("kind") if s.get("kind") in KINDS else "general"
        cites = sorted({c - 1 for c in s.get("citations") or [] if isinstance(c, int) and 1 <= c <= len(hits)})
        text = s["text"].strip()
        english = s.get("en") if isinstance(s.get("en"), str) and s["en"].strip() else None
        if kind == "evidence":
            ok = bool(cites) and answer._supported(english or text, [hits[c] for c in cites], use_decide)
        elif kind in ("plan", "data"):
            ok = _numbers(english or text) <= allowed
        else:
            ok, cites = True, []
        if not ok:
            dropped += 1
            continue
        kept.append({"text": text, "citations": cites, "kind": kind}
                    | ({"en": english.strip()} if kind == "evidence" and english and english.strip() != text else {}))
    return kept, dropped


def converse(retriever: Retriever, history: list[dict], plan_text: str, results: str, country: str | None) -> dict:
    """An Ask-shaped answer to the last message of the conversation (see the module docstring)."""
    message = history[-1]["content"]
    hits = find_passages(retriever, message, country)
    raw = llm.complete(prompts.get("chat_converse"), _context(history, plan_text, results, hits), max_tokens=900)
    first = (f"Written by {llm.model_name()} as the planning assistant, from the conversation, your plan"
             f"{' and its forecast' if results else ''} and {len(hits)} passages found for your message.")
    built_from = [answer.basis("conversation", f"The last {min(len(history), HISTORY)} messages")]
    if plan_text:
        built_from.append(answer.basis("plan", "Your plan"))
    if results:
        built_from.append(answer.basis("forecast", "Its forecast"))
    if hits:
        built_from.append(answer.basis("passages", answer._reports(hits), "found for your message"))
    return assemble(retriever, raw, hits, f"{plan_text}\n{results}", first, built_from)


def assemble(retriever: Retriever, raw: str, hits: list[Hit], grounding: str, first: str,
             built_from: list[dict] | None = None) -> dict:
    """The model's reply checked sentence by sentence and shaped as an Ask answer, with caveats saying what was checked
    and a provenance (what it was built from) for the card under it."""
    sentences = _parse(raw)
    use_decide = decide.available()
    if sentences is None:      # not the JSON asked for: show the reply as general text rather than nothing
        sentences = [{"text": raw.strip()[:1500], "kind": "general"}] if raw.strip() else []
    kept, dropped = check(sentences, hits, grounding, use_decide)
    used = sorted({c for s in kept for c in s["citations"]})
    remap = {c: i for i, c in enumerate(used)}
    for s in kept:
        s["citations"] = [remap[c] for c in s["citations"]]
    cited = [hits[c] for c in used]
    caveats = [first]
    if used:
        caveats.append(f"Sentences with a number cite the reports; each was checked against its passages by "
                       f"{'the decision model ' + decide.api_base() if use_decide else 'word overlap'}.")
    if any(s["kind"] == "plan" for s in kept):
        caveats.append("Sentences about your plan use only its own figures (checked number by number).")
    if any(s["kind"] == "data" for s in kept):
        caveats.append("Sentences marked engine data use only figures the engine returned (checked number by number).")
    if any(s["kind"] == "general" for s in kept):
        caveats.append("Sentences marked general are general guidance, not taken from the reports or your plan.")
    if dropped:
        caveats.append(f"{dropped} sentence{'s' if dropped > 1 else ''} not supported by the data were left out.")
    caveats += answer.conflict_notes(retriever, cited)
    return {"answer": kept, "citations": [answer.citation(h) for h in cited], "unsupported": not kept,
            "fallback": None, "meta": answer.meta(caveats), "provenance": answer.provenance(llm.model_name(), built_from or [], kept)}
