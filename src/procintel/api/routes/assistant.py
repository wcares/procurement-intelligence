"""Planning chat: one call turns the planner's latest message into a checked edit of the plan (procintel.assistant).

The server keeps nothing between calls. Statistics and evidence questions are answered by the endpoints that already
exist (/dashboard/ranking, /ask); this one only decides which is needed and hands back the question to put to it."""
from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, HTTPException

from procintel.api.schemas import PlanChatRequest, SummarizeRequest
from procintel.api.state import state
from procintel.assistant import context, interpret, resolve
from procintel.core import llm, prompts

router = APIRouter()

FULL_REPLY = ("This conversation has reached the model's length limit. Summarize it to continue in the same conversation, "
              "or start a new one; your plan stays.")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*\.?\d*", text)}


def _grounded(reply: str, *sources: str) -> bool:
    """Every number in the reply appears in what the model was given: it may explain the results, not invent them."""
    allowed = set().union(*(_numbers(s) for s in sources))
    return _numbers(reply) <= allowed


@router.post("/assistant/plan")
def post_plan_chat(req: PlanChatRequest) -> dict:
    s = state()
    options = s.options
    today = date.today()
    plan = req.plan.model_dump()
    history = [m.model_dump() for m in req.messages]
    system, fixed = interpret.fixed_prompt(options, interpret.with_names(plan, options), req.results, today)
    usage = context.usage(system + fixed, history)
    if usage["full"]:
        return {"intent": "other", "reply": FULL_REPLY, "plan": plan, "changes": [], "assumptions": [], "notes": [],
                "needs": [], "evidenceQuestion": None, "statistic": None, "context": usage}
    if not llm.available():
        raise HTTPException(503, "no language model is configured")
    try:
        raw = interpret.interpret(history, options, interpret.with_names(plan, options), req.results, today)
    except Exception as e:  # server down, timeout, a cut answer: the planner can retry or use the manual form
        raise HTTPException(502, f"the language model did not answer: {e}") from e
    r = resolve.resolve(raw, options, plan, today)
    if r["intent"] == "update_plan":
        reply = resolve.compose_reply(r)
    elif r["intent"] == "explain_plan":
        reply = r["modelReply"]
        if not req.results or not _grounded(reply, req.results, str(plan)):
            reply = ("I can only answer that from the forecast, and " + ("it does not contain what you asked about:\n" + req.results
                     if req.results else "there is none yet. Add packages and I will forecast them."))
    else:
        reply = r["modelReply"] or "Tell me about the project you want to plan, for example the country and what you will buy."
        if r["notes"]:
            reply = f"{reply} {' '.join(r['notes'])}"
    r.pop("modelReply")
    return {**r, "reply": reply, "context": context.usage(system + fixed, history + [{"role": "assistant", "content": reply}])}


@router.post("/assistant/summarize")
def post_summarize(req: SummarizeRequest) -> dict:
    """The conversation compacted into a short summary, which the page then sends in place of the earlier messages."""
    if not llm.available():
        raise HTTPException(503, "no language model is configured")
    transcript = "\n".join(f"{'Planner' if m.role == 'user' else 'Assistant'}: {m.content}" for m in req.messages)
    try:
        summary = llm.complete(prompts.get("chat_summary"), transcript, max_tokens=400).strip()
    except Exception as e:  # server down or timeout: the planner can retry or start a new conversation
        raise HTTPException(502, f"the language model did not answer: {e}") from e
    if not summary:
        raise HTTPException(502, "the language model returned no summary")
    return {"summary": summary}
