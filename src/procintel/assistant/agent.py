"""The planning chat as an agent: a model that can call tools (procintel.assistant.tools) decides itself what to look
up, possibly in several steps, and then answers; the answer is checked like every chat answer
(procintel.assistant.converse.assemble: cited sentences against their passages, figures against the plan and what the
tools returned, general advice labelled).

Used when the answer model can call tools (procintel.core.llm.supports_tools: Claude and other hosted models);
PROCINTEL_CHAT_TOOLS=off turns it off, =on forces it. Otherwise the chat keeps its earlier path (interpret, then
converse), so switching to a model without tool calling never breaks the chat.
"""
from __future__ import annotations

import json
import os
from datetime import date

from procintel.assistant import converse, tools
from procintel.core import llm, prompts

MAX_STEPS = 6          # rounds of tool calls before the model must answer
HISTORY = 10           # last messages of the conversation sent
MESSAGE_CHARS = 2000
TOOL_RESULT_CHARS = 8000


def enabled() -> bool:
    mode = os.environ.get("PROCINTEL_CHAT_TOOLS", "auto").strip().lower()
    if mode == "off":
        return False
    return mode == "on" or llm.supports_tools()


def _calls(message) -> list:
    return list(getattr(message, "tool_calls", None) or [])


def _as_dict(message) -> dict:
    """The assistant message with its tool calls, to send back with the tools' results."""
    return {"role": "assistant", "content": message.content or None,
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments or "{}"}}
                           for c in _calls(message)]}


def run(state, history: list[dict], plan: dict, results: str, today: date | None = None) -> dict:
    """One chat turn: {answer (Ask-shaped, checked), steps, plan, changes, assumptions, needs, notes, statistics}."""
    today = today or date.today()
    sess = tools.Session(state=state, plan=plan, results=results, today=today)
    schemas = [t.schema() for t in tools.TOOLS.values()]
    messages = [{"role": "system", "content": prompts.get("chat_agent", today=today.isoformat())}]
    messages += [{"role": m["role"], "content": m["content"][:MESSAGE_CHARS]} for m in history[-HISTORY:]]
    final = ""
    for _ in range(MAX_STEPS):
        msg = llm.chat(messages, schemas, max_tokens=1500)
        calls = _calls(msg)
        if not calls:
            final = msg.content or ""
            break
        messages.append(_as_dict(msg))
        for c in calls:
            out = tools.run(sess, c.function.name, c.function.arguments)
            messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(out, default=str)[:TOOL_RESULT_CHARS]})
    else:   # still calling tools: ask for the answer from what it has
        messages.append({"role": "user", "content": "Answer now from what the tools returned, in the JSON format asked for."})
        final = llm.chat(messages, None, max_tokens=1500).content or ""
    from procintel.assistant import interpret
    grounding = "\n".join([interpret.plan_summary(interpret.with_names(sess.plan, state.options)), results, *sess.outputs])
    first = (f"Written by {llm.model_name()} as the planning assistant, using the engine's tools"
             f"{': ' + '; '.join(sess.steps) if sess.steps else ' (none were needed)'}.")
    used = [converse.answer.basis("conversation", f"The last {min(len(history), HISTORY)} messages")] + sess.used
    answer = converse.assemble(state.retriever, final, sess.hits, grounding, first, used)
    return {"answer": answer, "steps": sess.steps, "plan": sess.plan, "changes": sess.changes,
            "assumptions": sess.assumptions, "needs": sess.needs, "notes": sess.notes, "statistics": sess.statistics}
