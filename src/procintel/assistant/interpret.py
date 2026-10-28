"""Ask the language model what a message means for the plan; it answers in JSON, which resolve.py then checks."""
from __future__ import annotations

import json
import re
from datetime import date

from procintel.assistant import context
from procintel.core import llm

TYPES = {"works": "CW", "goods": "GO", "consulting": "CS", "non_consulting": "NC"}

SYSTEM = """You help a procurement planner build a project plan by chat. Read the planner's latest message and answer with ONE JSON
object that lists the changes it asks for. Never invent values the planner did not give; use null for anything not said.

JSON shape:
{"intent": "update_plan" | "ask_evidence" | "ask_statistics" | "explain_plan" | "other",
 "country": <exact name from the COUNTRIES list, or null>,
 "start": <"YYYY-MM-DD" or null>, "deadline": <"YYYY-MM-DD" or null>, "deadline_months": <whole months after the start, or null>,
 "packages": [{"name": <short label>, "action": "add" | "update" | "remove",
               "type": "works" | "goods" | "consulting" | "non_consulting" | null,
               "method": <code from METHODS or null>, "value_usd": <number or null>,
               "sector": <exact name from SECTORS or null>, "description": <short text or null>,
               "after": <name of the package that must be awarded first, or null>}],
 "evidence_question": <a self-contained question, only when intent is ask_evidence, else null>,
 "statistic": <only when intent is ask_statistics, else null: {"measure": <key from MEASURES>, "group": "country" | "sector" | "method"}>,
 "reply": <one or two short sentences to the planner>}

Rules:
- intent "update_plan": the message adds, changes or removes packages, or sets the country, start or deadline.
- intent "ask_evidence": the message asks what happened or goes wrong in past projects, or why; write evidence_question so it makes sense alone (add the country or type from the plan if the message only implies it).
- intent "ask_statistics": the message asks which countries, sectors or methods were slowest, riskiest or most often re-tendered in the past; pick the closest measure key and one of the groupings listed for it in MEASURES. If no measure fits, use "ask_evidence" instead.
- intent "explain_plan": the message asks about the plan's own results (dates, bottleneck, risks); answer ONLY from RESULTS, quote its numbers exactly, and say so if RESULTS is empty.
- intent "other": greetings or anything else; reply briefly and say what you can do.
- To change an existing package use action "update" and the same name as in PLAN; a package not in PLAN is "add".
- Types: works = construction or civil works; goods = equipment, vehicles, supplies, IT hardware; consulting = studies, design, supervision, advisory; non_consulting = services that are not advice.
- value_usd is a plain number in US dollars: "2.5 million" is 2500000, "800k" is 800000.
- "within 12 months" or "in a year" is deadline_months 12. Resolve dates with TODAY; a month with no day is its first day.
- reply: if the planner has not said which country, ask for it; do not ask for anything else. Say what you understood in a few words.
Answer with the JSON only."""

EXAMPLES = """Examples:
Message: "Plan a roads project in Kenya, about 5 million, then supervision consultants after the works"
{"intent":"update_plan","country":"Republic of Kenya","start":null,"deadline":null,"deadline_months":null,"packages":[{"name":"Road works","action":"add","type":"works","method":null,"value_usd":5000000,"sector":"Rural and Inter-Urban Roads","description":"road works","after":null},{"name":"Supervision","action":"add","type":"consulting","method":null,"value_usd":null,"sector":null,"description":"works supervision","after":"Road works"}],"evidence_question":null,"statistic":null,"reply":"I added road works and the supervision consultants that follow them."}
Message: "why do road tenders go wrong in Kenya?"
{"intent":"ask_evidence","country":null,"start":null,"deadline":null,"deadline_months":null,"packages":[],"evidence_question":"What typically goes wrong with road works tenders in Kenya?","statistic":null,"reply":"Let me look at what past reports say."}
Message: "which procurement methods get re-tendered most?"
{"intent":"ask_statistics","country":null,"start":null,"deadline":null,"deadline_months":null,"packages":[],"evidence_question":null,"statistic":{"measure":"rebid","group":"method"},"reply":"Here is how often projects that used each method were re-tendered."}
Message: "hi"
{"intent":"other","country":null,"start":null,"deadline":null,"deadline_months":null,"packages":[],"evidence_question":null,"statistic":null,"reply":"Hello. Tell me about the project you want to plan, for example the country and what you will buy."}"""


def measure_labels() -> dict[str, str]:
    """The Overview's measures, key to label: the only statistics the chat may offer."""
    from procintel.insights.dashboard import MEASURES
    return {k: m.label for k, m in MEASURES.items()}


def with_names(plan: dict, options: dict) -> dict:
    """The plan with the country's and the predecessors' names added, for the prompt (the plan itself keeps codes and ids)."""
    names = {p["id"]: p["name"] for p in plan.get("packages", [])}
    country = next((c["name"] for c in options["countries"] if c["code"] == plan.get("countryCode")), None)
    return {**plan, "countryName": country,
            "packages": [{**p, "afterName": names.get(p.get("after"))} for p in plan.get("packages", [])]}


def measure_groups() -> dict[str, list[str]]:
    """Which groupings each Overview measure is counted for (a method is a package attribute, so a project-level measure cannot use it)."""
    from procintel.insights.dashboard import measures
    return {m["key"]: m["groups"] for m in measures()}


def plan_summary(plan: dict) -> str:
    if not plan.get("packages"):
        return "(empty)"
    lines = [f"country: {plan.get('countryName') or 'not set'}; start: {plan.get('projectStart')}; deadline: {plan.get('deadline') or 'none'}"]
    for p in plan["packages"]:
        after = f"; after: {p['afterName']}" if p.get("afterName") else ""
        value = f"; value: {p['estimatedValueUsd']:,.0f} USD" if p.get("estimatedValueUsd") else ""
        lines.append(f"- {p['name']}: {p['procGroup']} {p['methodCode']}{value}{after}")
    return "\n".join(lines)


def fixed_prompt(options: dict, plan: dict, results: str, today: date) -> tuple[str, str]:
    """(system, the part of the user prompt that does not depend on the conversation)."""
    countries = "; ".join(c["name"] for c in options["countries"])
    methods = "; ".join(f"{m['code']} ({m['label']}; for {','.join(m['procGroups'])})" for m in options["methods"])
    sectors = "; ".join(options["sectors"])
    groups = measure_groups()
    measures = "; ".join(f"{k} ({label}; by {'/'.join(groups.get(k, []))})" for k, label in (options.get("measures") or measure_labels()).items())
    fixed = (f"TODAY: {today.isoformat()}\nCOUNTRIES: {countries}\nMETHODS: {methods}\nSECTORS: {sectors}\nMEASURES: {measures}\n"
             f"PLAN:\n{plan_summary(plan)}\nRESULTS:\n{results or '(none yet)'}\n{EXAMPLES}")
    return SYSTEM, fixed


def conversation_text(history: list[dict]) -> str:
    return "\n".join(f"{'Planner' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in history)


def parse(raw: str) -> dict:
    """The first JSON object in the model's text; an empty dict when there is none."""
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {}
    try:
        out = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    return out if isinstance(out, dict) else {}


def interpret(history: list[dict], options: dict, plan: dict, results: str = "", today: date | None = None) -> dict:
    """The model's reading of the latest message (history ends with it). Raises if no model is configured."""
    system, fixed = fixed_prompt(options, plan, results, today or date.today())
    user = f"{fixed}\n\nConversation so far:\n{conversation_text(history)}\n\nJSON for the planner's latest message:"
    return parse(llm.complete(system, user, temperature=0.0, max_tokens=700))
