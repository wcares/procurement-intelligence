"""Rules: when an event (and an optional field condition) happens, which actions run.

Default rules ship here (DEFAULT_RULES, docs/event-pipeline-design.md section 6). Rules edited on the Settings page
are saved to the data folder (paths.PIPELINE_RULES) after validation: known event types only, field conditions on
watched fields only, actions from the registry only, and no cycle in which an action's derived events lead back to
that action. dry_run() shows what a rule set would have done on the last days' events. reset() restores the defaults.
plan() turns a batch of events into one ordered list of actions with the keys each
should touch: an action asked for by many events runs once (coalesced), in the registry's order, which follows the
data's dependencies (raw rows before the tables built from them, tables before the reload).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from procintel.core import paths


@dataclass(frozen=True)
class Rule:
    id: str
    on: tuple[str, ...]                   # event types, e.g. ("Notice.added", "Notice.changed")
    do: tuple[str, ...]                   # action names, from procintel.pipeline.actions.ACTIONS
    fields: tuple[str, ...] = field(default=())   # for .changed events: fire only when one of these fields changed
    enabled: bool = True

    def matches(self, event: dict) -> bool:
        if not self.enabled or event["type"] not in self.on:
            return False
        if self.fields and event["type"].endswith(".changed"):
            return bool(set(self.fields) & set(event.get("changed") or []))
        return True


DEFAULT_RULES = [
    Rule("notices-update-packages", ("Notice.added", "Notice.changed"),
         ("apply_notices", "rebuild_tables", "rebuild_firms")),
    Rule("documents-ingest", ("Document.added", "Document.changed"),
         ("ingest_documents", "rebuild_tables", "rebuild_firms", "chunk_documents")),
    Rule("passages-index", ("Passages.changed",), ("index_passages", "document_checks")),
    Rule("projects-update", ("Project.changed",), ("apply_projects", "rebuild_tables", "sector_links"),
         fields=("status", "sector", "closing_date", "board_approval", "commitment_usd")),
    Rule("contracts-award-dates", ("ContractAward.added", "ContractAward.changed", "ContractAward.removed"),
         ("apply_contracts", "fill_award_dates")),
    Rule("indicators-governance", ("Indicator.added", "Indicator.changed", "Indicator.removed"),
         ("apply_indicators",)),
    Rule("awards-check-model", ("Package.award_changed",), ("drift_check",)),
    Rule("data-reload", ("Data.updated",), ("reload_backend",)),
]


def plan(events: list[dict], rules: list[Rule], order: list[str]) -> tuple[list[tuple[str, list[str]]], dict]:
    """([(action, keys)] in registry order, {rule id: number of events it matched})."""
    keys: dict[str, set[str]] = {}
    fired: dict[str, int] = {}
    for e in events:
        for r in rules:
            if r.matches(e):
                fired[r.id] = fired.get(r.id, 0) + 1
                for a in r.do:
                    keys.setdefault(a, set()).add(e["key"])
    unknown = set(keys) - set(order)
    if unknown:
        raise ValueError(f"rules name unknown actions: {sorted(unknown)}")
    return [(a, sorted(keys[a])) for a in order if a in keys], fired


DERIVED_EVENTS = ("Package.award_changed", "Data.updated", "Documents.changed", "Passages.changed")


def event_types(entity_types: dict) -> list[str]:
    return [f"{n}.{k}" for n in entity_types for k in ("added", "changed", "removed")] + list(DERIVED_EVENTS)


def to_dict(r: Rule) -> dict:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(r).items()}


def from_dict(d: dict) -> Rule:
    return Rule(id=str(d.get("id", "")).strip(), on=tuple(d.get("on") or ()), do=tuple(d.get("do") or ()),
                fields=tuple(d.get("fields") or ()), enabled=bool(d.get("enabled", True)))


def validate(rules: list[Rule], entity_types: dict, actions: dict) -> dict[str, str]:
    """{rule id (or "(set)"): problem}; empty when the rule set can be saved."""
    errors: dict[str, str] = {}
    known = set(event_types(entity_types))
    ids = [r.id for r in rules]
    for r in rules:
        problems = []
        if not r.id:
            problems.append("a rule needs an id")
        if ids.count(r.id) > 1:
            problems.append("the id is used twice")
        if not r.on:
            problems.append("no event chosen")
        if unknown := [e for e in r.on if e not in known]:
            problems.append(f"unknown events {unknown}")
        if not r.do:
            problems.append("no action chosen")
        if unknown := [a for a in r.do if a not in actions]:
            problems.append(f"unknown actions {unknown}")
        if r.fields:
            changed = [e.split(".")[0] for e in r.on if e.endswith(".changed") and e.split(".")[0] in entity_types]
            if not changed:
                problems.append("a field condition needs a .changed event")
            watched = {f for t in changed for f in entity_types[t].watched}
            if unknown := [f for f in r.fields if f not in watched]:
                problems.append(f"fields not watched for these events: {unknown}")
        if problems:
            errors[r.id or "(new rule)"] = "; ".join(problems)
    if not errors and (cycle := find_cycle(rules, actions)):
        errors["(set)"] = "the rules form a cycle: " + " -> ".join(cycle)
    return errors


def find_cycle(rules: list[Rule], actions: dict) -> list[str] | None:
    """A path action -> derived event -> rule -> ... -> the same action, if the enabled rules allow one."""
    nxt = {a: sorted({b for e in actions[a].emits for r in rules if r.enabled and e in r.on for b in r.do if b in actions})
           for a in actions}
    for start in actions:
        stack = [(start, [start])]
        while stack:
            a, path = stack.pop()
            for b in nxt.get(a, []):
                if b == start:
                    return path + [b]
                if b not in path:
                    stack.append((b, path + [b]))
    return None


def active() -> list[Rule]:
    f = paths.PIPELINE_RULES
    if not f.exists():
        return list(DEFAULT_RULES)
    return [from_dict(d) for d in json.loads(f.read_text())["rules"]]


def customised() -> bool:
    return paths.PIPELINE_RULES.exists()


def save(rules: list[Rule], entity_types: dict, actions: dict) -> dict[str, str]:
    errors = validate(rules, entity_types, actions)
    if not errors:
        paths.PIPELINE_RULES.parent.mkdir(parents=True, exist_ok=True)
        paths.PIPELINE_RULES.write_text(json.dumps({"rules": [to_dict(r) for r in rules]}, indent=1))
    return errors


def reset() -> None:
    paths.PIPELINE_RULES.unlink(missing_ok=True)


def dry_run(rules: list[Rule], batches: dict[str, list[dict]], order: list[str]) -> dict:
    """What these rules would have done on past batches of events (procintel.pipeline.store.recent_batches):
    times each rule fires, and per action how many events asked for it and how many runs that coalesces to."""
    fired: dict[str, int] = {}
    asked: dict[str, int] = {}
    runs: dict[str, int] = {}
    for events in batches.values():
        steps, f = plan(events, rules, order)
        for rid, n in f.items():
            fired[rid] = fired.get(rid, 0) + n
        for a, keys in steps:
            asked[a] = asked.get(a, 0) + len(keys)
            runs[a] = runs.get(a, 0) + 1
    return {"batches": len(batches), "events": sum(len(v) for v in batches.values()), "fired": fired,
            "actions": {a: {"events": asked[a], "runs": runs[a]} for a in order if a in runs}}


DRY_RUN_DAYS = timedelta(days=7)
