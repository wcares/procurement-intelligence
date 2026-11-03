"""Planning chat: one call turns the planner's latest message into a checked edit of the plan (procintel.assistant).

The server keeps nothing between calls. Statistics and evidence questions are answered by the endpoints that already
exist (/dashboard/ranking, /ask); this one only decides which is needed and hands back the question to put to it."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from procintel.api.schemas import PlanChatRequest, SummarizeRequest
from procintel.api.state import state
from procintel.api import security
from procintel.answering import answer
from procintel.assistant import agent, context, converse, interpret, resolve
from procintel.auth import service
from procintel.learning import feedback
from procintel.core import llm, prompts

router = APIRouter()

FULL_REPLY = ("This conversation has reached the model's length limit. Summarize it to continue in the same conversation, "
              "or start a new one; your plan stays.")


@router.post("/assistant/plan")
def post_plan_chat(req: PlanChatRequest, request: Request) -> dict:
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
    if agent.enabled():
        # a model that calls tools decides itself what to look up or change (procintel.assistant.agent)
        try:
            out = agent.run(s, history, plan, req.results, today)
        except Exception as e:  # server down, timeout: the planner can retry
            raise HTTPException(502, f"the language model did not answer: {e}") from e
        feedback.log_response("chat", {"message": history[-1]["content"]}, out["answer"],
                              user_id=service.pseudonym(security.user_of(request)))
        reply = " ".join(x["text"] for x in out["answer"]["answer"]) or "I could not find anything in the data for that."
        return {"intent": "chat", "reply": reply, "plan": out["plan"], "changes": out["changes"],
                "assumptions": out["assumptions"], "notes": out["notes"], "needs": out["needs"],
                "evidenceQuestion": None, "statistic": None, "answer": out["answer"], "steps": out["steps"],
                "statistics": out["statistics"],
                "context": context.usage(system + fixed, history + [{"role": "assistant", "content": reply}])}
    try:
        raw = interpret.interpret(history, options, interpret.with_names(plan, options), req.results, today)
    except Exception as e:  # server down, timeout, a cut answer: the planner can retry or use the manual form
        raise HTTPException(502, f"the language model did not answer: {e}") from e
    r = resolve.resolve(raw, options, plan, today)
    # where a reply that is not an Ask-shaped answer came from (the page shows it under the reply)
    read = [answer.basis("message", "Your message, read by " + (llm.model_name() or "the model")), answer.basis("plan", "Your plan")]
    if r["intent"] == "update_plan":
        reply = resolve.compose_reply(r)
        r["provenance"] = answer.provenance(None, read + [answer.basis("plan", "The changes made to it, checked against the data's countries and methods")])
    elif r["intent"] in ("explain_plan", "other"):
        # free conversation: the planning assistant answers from the conversation, the plan, its forecast and the
        # reports, each sentence checked (procintel.assistant.converse); the page shows it like an Ask answer
        try:
            out = converse.converse(s.retriever, history, interpret.plan_summary(interpret.with_names(plan, options)),
                                    req.results, plan.get("countryCode"))
        except Exception as e:  # the model failed: say so rather than lose the turn
            raise HTTPException(502, f"the language model did not answer: {e}") from e
        feedback.log_response("chat", {"message": history[-1]["content"]}, out,
                              user_id=service.pseudonym(security.user_of(request)))
        r["intent"], r["answer"] = "chat", out
        reply = " ".join(x["text"] for x in out["answer"]) or "I could not find anything in the data for that."
    else:
        reply = r["modelReply"] or "Tell me about the project you want to plan, for example the country and what you will buy."
        if r["notes"]:
            reply = f"{reply} {' '.join(r['notes'])}"
        r["provenance"] = answer.provenance(llm.model_name() if r["modelReply"] else None, read)
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
