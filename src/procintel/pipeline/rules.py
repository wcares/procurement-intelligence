"""Rules: when an event (and an optional field condition) happens, which actions run.

Default rules ship here (DEFAULT_RULES, docs/event-pipeline-design.md section 6); editing them from the Settings page
is step 3 of the build plan. plan() turns a batch of events into one ordered list of actions with the keys each
should touch: an action asked for by many events runs once (coalesced), in the registry's order, which follows the
data's dependencies (raw rows before the tables built from them, tables before the reload).
"""
from __future__ import annotations

from dataclasses import dataclass, field


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
    Rule("notices-update-packages", ("Notice.added", "Notice.changed"), ("apply_notices", "rebuild_tables")),
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
