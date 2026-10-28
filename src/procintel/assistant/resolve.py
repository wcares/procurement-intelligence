"""Check what the model proposed against the data's own vocabulary and apply it to the plan.

Nothing the model says reaches the plan unchecked: a country must be one the data has, a method one used for that kind
of purchase, a value a positive number, a link a package that exists. What cannot be checked becomes a question for the
planner, never a guess; what is filled in by default is reported as an assumption so the planner can correct it.
"""
from __future__ import annotations

import calendar
import difflib
import re
from datetime import date

from procintel.assistant.interpret import TYPES, measure_labels

INTENTS = ("update_plan", "ask_evidence", "ask_statistics", "explain_plan", "other")
GROUPS = ("country", "sector", "method")
MAX_PACKAGES = 12
GROUP_LABEL = {"CW": "civil works", "GO": "goods", "CS": "consulting services", "NC": "non-consulting services"}

# Method assumed when the planner does not name one: the usual choice for that kind of purchase in the data.
# Configuration, not logic: change it here (goods above the threshold use the competitive method).
DEFAULT_METHOD = {"CW": "RFB", "GO": "RFQ", "CS": "QCBS", "NC": "RFB"}
GOODS_RFB_FROM_USD = 500_000

# Everyday names that differ from the data's official ones (kept short: only names a planner is likely to type).
ALIASES = {"turkey": "TR", "laos": "LA", "lao pdr": "LA", "ivory coast": "CI", "gambia": "GM", "palestine": "GZ",
           "east timor": None}

_FILLER = re.compile(r"\b(the|of|republic|kingdom|federal|federative|democratic|people's|peoples|islamic|socialist|oriental|"
                     r"united|state|states|federated|commonwealth|co-operative|cooperative|lao|arab|plurinational)\b")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", _FILLER.sub(" ", re.sub(r"[^a-z' ]", " ", text.lower()))).strip()


def match_country(name: str | None, options: dict) -> str | None:
    """Country code for a name as the model or the planner wrote it: exact, then without titles ("Republic of"), then a
    close spelling. None when nothing matches well enough: the planner is asked, not guessed for."""
    if not name or not name.strip():
        return None
    want = name.strip().lower()
    countries = options["countries"]
    for c in countries:
        if want in (c["name"].lower(), c["code"].lower()):
            return c["code"]
    if want in ALIASES:
        return ALIASES[want]
    key = _norm(name)
    if not key:
        return None
    keyed = {c["code"]: _norm(c["name"]) for c in countries}
    for code, k in keyed.items():
        if k == key:
            return code
    # every word typed must be in the country's name ("congo" fits Republic of Congo; "dr congo" fits nothing)
    inside = [code for code, k in keyed.items() if k and set(key.split()) <= set(k.split())]
    if len(inside) == 1:
        return inside[0]
    close = difflib.get_close_matches(key, list(keyed.values()), n=1, cutoff=0.8)
    return next((code for code, k in keyed.items() if close and k == close[0]), None)


def add_months(day: date, months: int) -> date:
    m = day.month - 1 + months
    y, m = day.year + m // 12, m % 12 + 1
    return date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


def _iso(text) -> str | None:
    try:
        return date.fromisoformat(str(text)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def money(v: float) -> str:
    return f"US${v / 1e6:,.1f}M" if v >= 1e6 else f"US${v / 1e3:,.0f}k" if v >= 1e3 else f"US${v:,.0f}"


def _method_label(code: str, options: dict) -> str:
    return next((m["label"] for m in options["methods"] if m["code"] == code), code)


def _valid_method(code, group: str, options: dict) -> bool:
    return any(m["code"] == code and group in m["procGroups"] for m in options["methods"])


def _default_method(group: str, value: float | None) -> str:
    if group == "GO" and value and value >= GOODS_RFB_FROM_USD:
        return "RFB"
    return DEFAULT_METHOD[group]


def _find(packages: list[dict], name: str, loose: bool = True) -> dict | None:
    """The package a name refers to: an exact name, or (loose, for update/remove/links) the one package whose name
    contains it. Two candidates is not a match: "P1" must not pick "P10"."""
    want = name.strip().lower()
    for p in packages:
        if p["name"].lower() == want:
            return p
    if loose and want:
        hits = [p for p in packages if want in p["name"].lower() or p["name"].lower() in want]
        if len(hits) == 1:
            return hits[0]
    return None


def _new_id(packages: list[dict]) -> str:
    n = 1 + max((int(p["id"][1:]) for p in packages if re.fullmatch(r"p\d+", p["id"])), default=0)
    return f"p{n}"


def resolve(raw: dict, options: dict, plan: dict, today: date) -> dict:
    """The checked reading of one message: the new plan, what changed, what was assumed, what to ask."""
    intent = raw.get("intent") if raw.get("intent") in INTENTS else "other"
    new = {"countryCode": plan.get("countryCode"), "projectStart": plan.get("projectStart") or today.isoformat(),
           "deadline": plan.get("deadline"), "packages": [dict(p) for p in plan.get("packages", [])]}
    changes: list[str] = []
    assumptions: list[str] = []
    notes: list[str] = []

    if intent == "update_plan":
        if raw.get("country"):
            code = match_country(str(raw["country"]), options)
            if code:
                if code != new["countryCode"]:
                    new["countryCode"] = code
                    changes.append(f"Country: {next(c['name'] for c in options['countries'] if c['code'] == code)}")
            else:
                notes.append(f"I don't have data for \"{raw['country']}\"; the data covers {len(options['countries'])} countries.")
        if (start := _iso(raw.get("start"))) and start != new["projectStart"]:
            new["projectStart"] = start
            changes.append(f"Project start: {start}")
        months = raw.get("deadline_months")
        deadline = _iso(raw.get("deadline"))
        if deadline is None and isinstance(months, (int, float)) and 1 <= months <= 120:
            deadline = add_months(date.fromisoformat(new["projectStart"]), int(months)).isoformat()
        if deadline and deadline != new["deadline"]:
            new["deadline"] = deadline
            changes.append(f"Deadline for all awards: {deadline}")

        pending_after: list[tuple[dict, str]] = []
        for item in (raw.get("packages") or [])[:MAX_PACKAGES]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()[:80]
            action = item.get("action") if item.get("action") in ("add", "update", "remove") else "add"
            existing = _find(new["packages"], name, loose=action != "add") if name else None
            if action == "remove":
                if existing:
                    new["packages"].remove(existing)
                    for p in new["packages"]:
                        if p.get("after") == existing["id"]:
                            p.pop("after")
                    changes.append(f"Removed {existing['name']}")
                else:
                    notes.append(f"There is no package called \"{name}\" to remove.")
                continue
            group = TYPES.get(item.get("type") or "")
            if existing is None:
                if group is None:
                    notes.append(f"Is \"{name or 'the new package'}\" works, goods, consulting or non-consulting services?")
                    continue
                if len(new["packages"]) >= MAX_PACKAGES:
                    notes.append(f"A plan holds at most {MAX_PACKAGES} packages.")
                    continue
                existing = {"id": _new_id(new["packages"]), "name": name or f"{GROUP_LABEL[group].capitalize()} package",
                            "procGroup": group, "methodCode": ""}
                new["packages"].append(existing)
                verb = "Added"
            else:
                verb = "Updated"
            before = (existing["procGroup"], existing["methodCode"], existing.get("estimatedValueUsd"))
            if group:
                existing["procGroup"] = group
            value = item.get("value_usd")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
                existing["estimatedValueUsd"] = float(value)
            method = item.get("method")
            if method and _valid_method(method, existing["procGroup"], options):
                existing["methodCode"] = method
            elif not existing["methodCode"] or not _valid_method(existing["methodCode"], existing["procGroup"], options):
                existing["methodCode"] = _default_method(existing["procGroup"], existing.get("estimatedValueUsd"))
                why = f"{method} is not used for {GROUP_LABEL[existing['procGroup']]}, so " if method else ""
                assumptions.append(f"{why}I assumed {_method_label(existing['methodCode'], options)} for {existing['name']}, the usual choice; tell me if it differs.")
            if item.get("sector") in options["sectors"]:
                existing["sector"] = item["sector"]
            if isinstance(item.get("description"), str) and item["description"].strip():
                existing["description"] = item["description"].strip()[:2000]
            if item.get("after"):
                pending_after.append((existing, str(item["after"])))
            if verb == "Added" or before != (existing["procGroup"], existing["methodCode"], existing.get("estimatedValueUsd")):
                bits = [GROUP_LABEL[existing["procGroup"]], _method_label(existing["methodCode"], options)]
                if existing.get("estimatedValueUsd"):
                    bits.append(money(existing["estimatedValueUsd"]))
                changes.append(f"{verb} {existing['name']} ({', '.join(bits)})")
        for pkg, target_name in pending_after:   # links last, so a package may follow one added in the same message
            target = _find(new["packages"], target_name)
            if target and target["id"] != pkg["id"]:
                pkg["after"] = target["id"]
                changes.append(f"{pkg['name']} starts after {target['name']} is awarded")
            else:
                notes.append(f"I could not find a package called \"{target_name}\" for {pkg['name']} to follow.")

    needs = []
    if intent == "update_plan" and new["packages"] and not new["countryCode"]:
        needs.append("country")
    stat = raw.get("statistic") if isinstance(raw.get("statistic"), dict) else None
    if intent == "ask_statistics":
        ok = stat and stat.get("measure") in measure_labels() and stat.get("group") in GROUPS
        stat = {"measure": stat["measure"], "group": stat["group"]} if ok else None
        if not stat:
            intent = "ask_evidence"   # no Overview measure fits: the reports may still answer it
    evidence = str(raw["evidence_question"]).strip()[:1000] if raw.get("evidence_question") else None
    if intent == "ask_evidence" and not evidence:
        intent = "other"
    return {"intent": intent, "plan": new, "changes": changes, "assumptions": assumptions, "notes": notes, "needs": needs,
            "evidenceQuestion": evidence if intent == "ask_evidence" else None, "statistic": stat if intent == "ask_statistics" else None,
            "modelReply": str(raw.get("reply") or "").strip()[:500]}


def compose_reply(r: dict) -> str:
    """The text for a plan edit, built from what was checked (never the model's own claims about the plan)."""
    parts: list[str] = []
    if r["changes"]:
        parts.append("Done: " + "; ".join(r["changes"]) + ".")
    parts += r["assumptions"] + r["notes"]
    if "country" in r["needs"]:
        parts.append("Which country is this project in?")
    if not parts:
        parts.append(r["modelReply"] or "I did not find a change to make. Tell me the country and what you will buy.")
    return " ".join(parts)
