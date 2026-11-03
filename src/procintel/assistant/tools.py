"""Tools the planning assistant can call (procintel.assistant.agent).

One registry, like the connectors: a tool is a name, a description the model reads, a JSON schema of its inputs and a
function. Adding a feature to the chat is one more @tool below; the agent offers every registered tool to the model.

Every tool reads the engine's own data. update_plan changes only this conversation's plan (the page forecasts it and
keeps it behind its link); no tool writes stored data. Passages a tool returns are numbered across the whole turn
(Session.cite), so the final answer cites them as [n] and each cited sentence is checked against them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from procintel.answering import answer
from procintel.answering.retrieve import Hit


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[..., dict]

    def schema(self) -> dict:
        """The tool as offered to the model (OpenAI function format; LiteLLM converts it for other providers)."""
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                                                  "parameters": self.parameters}}


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict, required: tuple[str, ...] = ()):
    """Register a tool: @tool(name, description, {param: json-schema}, required)."""
    def register(fn: Callable[..., dict]) -> Callable[..., dict]:
        TOOLS[name] = Tool(name, description, {"type": "object", "properties": properties, "required": list(required)}, fn)
        return fn
    return register


@dataclass
class Session:
    """What one chat turn's tools share: the engine's state, the conversation's plan, and what the tools found."""
    state: Any
    plan: dict
    results: str
    today: date
    hits: list[Hit] = field(default_factory=list)     # passages, numbered 1.. across the turn
    steps: list[str] = field(default_factory=list)    # what was done, in words, for the page
    outputs: list[str] = field(default_factory=list)  # every tool result, for checking the answer's numbers
    used: list[dict] = field(default_factory=list)    # what the answer is built from (answer.basis), for its card
    changes: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    needs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    statistics: list[dict] = field(default_factory=list)

    @property
    def options(self) -> dict:
        return self.state.options

    def cite(self, hits: list[Hit]) -> list[int]:
        """The passages' numbers for this turn (a passage seen before keeps its number)."""
        out = []
        for h in hits:
            known = next((i for i, x in enumerate(self.hits) if x.chunk_id == h.chunk_id), None)
            if known is None:
                self.hits.append(h)
                known = len(self.hits) - 1
            out.append(known + 1)
        return out

    def passages(self, hits: list[Hit]) -> list[dict]:
        return [{"n": n, "report": h.title, "project": f"{h.project_name} ({h.project_id})", "country": h.country_code,
                 "section": h.section, "text": h.text[:900]} for n, h in zip(self.cite(hits), hits)]


def _country(sess: Session, value: str | None) -> str | None:
    """A country code from a code or a name the data knows; None when it does not."""
    if not value:
        return None
    codes = {c["code"] for c in sess.options["countries"]}
    if value.upper() in codes:
        return value.upper()
    from procintel.assistant.resolve import match_country
    return match_country(value, sess.options)


@tool("search_reports",
      "Search World Bank completion and supervision reports for passages about past projects: what happened, what went "
      "wrong, why, lessons. Write the query in the reports' words (e.g. 'civil works contract delays contractor capacity'). "
      "Returns numbered passages; cite them as [n] in the answer.",
      {"query": {"type": "string", "description": "what to look for"},
       "country": {"type": "string", "description": "optional: a country name or two-letter code, to search its projects only"}},
      ("query",))
def search_reports(sess: Session, query: str, country: str | None = None) -> dict:
    code = _country(sess, country)
    hits = sess.state.retriever.search(query, k=6, country=code)
    if code and not hits:
        hits = sess.state.retriever.search(query, k=6)
    sess.steps.append(f'Searched the reports for "{query}"' + (f" ({code})" if code else ""))
    sess.used.append(answer.basis("passages", answer._reports(hits), f'found for "{query}"' + (f" in {code}" if code else "")))
    return {"passages": sess.passages(hits)}


@tool("assess_package",
      "Assess one planned procurement package from past packages: days from tender notice to contract award (typical "
      "and slow case), the chance it takes over 180 days, risk flags with their evidence, and lessons from past reports. "
      "procurement_type: CW civil works, GO goods, CS consulting services, NC non-consulting services. Method codes come "
      "from procurement_options.",
      {"country": {"type": "string", "description": "country name or two-letter code"},
       "procurement_type": {"type": "string", "enum": ["CW", "GO", "CS", "NC"]},
       "method": {"type": "string", "description": "method code, e.g. RFB, RFQ, QCBS, CQS"},
       "value_usd": {"type": "number", "description": "optional estimated value in US dollars"},
       "description": {"type": "string", "description": "optional: what is bought, in a few words"}},
      ("country", "procurement_type", "method"))
def assess_package(sess: Session, country: str, procurement_type: str, method: str, value_usd: float | None = None,
                   description: str | None = None) -> dict:
    from procintel.api.routes.assess import assessment
    from procintel.mcp_server import shape_assessment
    code = _country(sess, country)
    if not code:
        return {"error": f"no data for the country {country!r}"}
    body = {"countryCode": code, "procGroup": procurement_type, "methodCode": method.upper(), "sector": None,
            "estimatedValueUsd": value_usd, "description": description, "tenderReference": None, "projectId": None,
            "withPrecedents": True}
    out = shape_assessment(assessment(body))
    lessons = []
    for lesson in out.pop("lessons"):
        hit = sess.state.retriever.passage(lesson["passageId"])
        if hit:
            lessons += sess.passages([hit])
    out["lessons"] = lessons
    sess.steps.append(f"Assessed {procurement_type} by {method.upper()} in {code}" + (f", US${value_usd:,.0f}" if value_usd else ""))
    d = out["daysToAward"]
    sess.used.append(answer.basis("assessment", f"Assessment of {procurement_type} by {method.upper()} in {code}",
                                  f"{d['comparablePackages'] or 0} comparable packages ({d['comparedWith'] or 'all'}); "
                                  f"{len(out['risks'])} risk flags; {len(lessons)} lessons from the reports"))
    return out


@tool("procurement_options",
      "The procurement types and methods the data covers (method codes for assess_package and update_plan), and the "
      "number of countries.",
      {})
def procurement_options(sess: Session) -> dict:
    o = sess.options
    return {"types": o["procGroups"], "methods": [{"code": m["code"], "label": m["label"], "types": m["procGroups"]}
                                                  for m in o["methods"]],
            "countries": len(o["countries"])}


@tool("get_plan",
      "The planner's current plan (country, start, deadline, packages) and its forecast (dates, bottleneck, risks), as "
      "the page last computed it. Use it before answering about the plan.",
      {})
def get_plan(sess: Session) -> dict:
    from procintel.assistant import interpret
    sess.steps.append("Read your plan and its forecast")
    sess.used.append(answer.basis("plan", "Your plan and its forecast"))
    return {"plan": interpret.plan_summary(interpret.with_names(sess.plan, sess.options)),
            "forecast": sess.results or "(none yet: the plan has no packages, or they are not forecast yet)"}


@tool("update_plan",
      "Change the planner's plan: set the country, start or deadline, or add, update or remove packages. Values are "
      "checked against the data (unknown countries or methods become questions, defaults are reported). The page "
      "forecasts the new plan after your reply.",
      {"country": {"type": "string"}, "start": {"type": "string", "description": "YYYY-MM-DD"},
       "deadline": {"type": "string", "description": "YYYY-MM-DD"},
       "deadline_months": {"type": "integer", "description": "deadline as months after the start"},
       "packages": {"type": "array", "items": {"type": "object", "properties": {
           "name": {"type": "string"}, "action": {"type": "string", "enum": ["add", "update", "remove"]},
           "type": {"type": "string", "enum": ["works", "goods", "consulting", "non_consulting"]},
           "method": {"type": "string"}, "value_usd": {"type": "number"}, "sector": {"type": "string"},
           "description": {"type": "string"}, "after": {"type": "string", "description": "name of the package it follows"}},
           "required": ["name", "action"]}}})
def update_plan(sess: Session, **change) -> dict:
    from procintel.assistant import interpret, resolve
    raw = {"intent": "update_plan", "packages": [], **change}
    r = resolve.resolve(raw, sess.options, sess.plan, sess.today)
    sess.plan = r["plan"]
    sess.changes += r["changes"]
    sess.assumptions += r["assumptions"]
    sess.needs += r["needs"]
    sess.notes += r["notes"]
    sess.steps.append("Updated your plan: " + ("; ".join(r["changes"]) or "nothing changed"))
    sess.used.append(answer.basis("plan", "Your plan, as updated in this turn"))
    return {"changes": r["changes"], "assumptions": r["assumptions"], "questions": r["needs"], "notes": r["notes"],
            "plan": interpret.plan_summary(interpret.with_names(sess.plan, sess.options)),
            "forecast": "computed by the page after this reply"}


@tool("statistics",
      "Compare countries, sectors or methods on a measure from past projects (worst first): e.g. award delays, re-tender "
      "rates. Call procurement_options or try a measure key; unknown keys return the list.",
      {"measure": {"type": "string"}, "group": {"type": "string", "enum": ["country", "sector", "method"]}},
      ("measure", "group"))
def statistics(sess: Session, measure: str, group: str) -> dict:
    from procintel.assistant import interpret
    try:
        data = sess.state.dashboard.ranking(measure, group)
    except (KeyError, ValueError) as e:
        return {"error": str(e), "measures": interpret.measure_labels(), "groups_per_measure": interpret.measure_groups()}
    sess.statistics.append(data)
    sess.steps.append(f"Looked up {data['measure']['label']} by {data['groupLabel'].lower()}")
    rows = [r for r in data["rows"] if not r["few"]][:10]
    sess.used.append(answer.basis("statistics", f"{data['measure']['label']} by {data['groupLabel'].lower()}",
                                  f"{len(rows)} {data['groupLabel'].lower()} groups with enough projects, from past projects' records"))
    return {"measure": data["measure"]["label"], "unit": data["measure"].get("unit"), "by": data["groupLabel"],
            "worst_first": [{"name": r["label"], "value": r["value"], "projects": r["projects"]} for r in rows]}


def run(sess: Session, name: str, arguments: str | dict | None) -> dict:
    """Call a tool by name with the model's arguments; an unknown tool or a failure comes back as {"error"}."""
    t = TOOLS.get(name)
    if t is None:
        return {"error": f"no tool {name!r}; tools: {', '.join(TOOLS)}"}
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        out = t.run(sess, **args)
    except Exception as e:   # noqa: BLE001 - the model sees the failure and can try something else
        out = {"error": f"{type(e).__name__}: {e}"[:300]}
    sess.outputs.append(json.dumps(out, default=str))
    return out
