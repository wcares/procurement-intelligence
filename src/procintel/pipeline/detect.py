"""Change detection and batch execution, as two job kinds on the existing queue (procintel.jobs).

detect_changes (normal priority, queued hourly): for every entity type whose interval has passed, read the source,
compare with the stored state and record the events; a type seen for the first time is seeded from the database
without events. Then the default rules turn the batch's events into a plan, and one pipeline_batch job is queued.

pipeline_batch (normal priority): runs the plan's actions one per job step (so it pauses when the app is used), adds
the derived events they report (Package.award_changed, Data.updated) to the batch, and plans again: an action is
asked for at most once per batch, and only actions later in the registry order can be added, so a batch cannot loop.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterator

from procintel.pipeline import actions, entities, rules, store

DERIVED_PREFIXES = ("Package.", "Data.")


def due(entity_type: entities.EntityType, force: bool) -> bool:
    if force:
        return True
    last = store.overview(limit=0)["lastRun"].get(entity_type.name)
    return last is None or entities.now() - datetime.fromisoformat(last["ranAt"].rstrip("Z")) >= entity_type.every


def _context(name: str) -> dict:
    if name != "Notice":
        return {}
    dates = [f.get("notice_date") for _, f in store.states("Notice").values() if f.get("notice_date")]
    return {"newest_notice": max(dates)[:10] if dates else None}


def detect_steps(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    cur = cursor or {"batch": store.new_batch(), "done": [], "counts": {}}
    types = params.get("types") or list(entities.ENTITY_TYPES)
    for name in types:
        if name in cur["done"]:
            continue
        et = entities.ENTITY_TYPES[name]
        if due(et, params.get("force", False)):
            known = store.states(name)
            if not known:
                n = store.seed(name, et.watched, et.read_db())
                store.log_detection(cur["batch"], name, n, 0, "first run: state seeded from the database")
                cur["counts"][name] = 0
            else:
                rows, complete = et.read_source(_context(name))
                events = store.diff(name, et.watched, rows, known, complete)
                store.record(name, cur["batch"], events, list(rows))
                store.log_detection(cur["batch"], name, len(rows), len(events),
                                    "" if complete else "newest items only (no removals from a partial read)")
                cur["counts"][name] = len(events)
        cur["done"].append(name)
        yield cur
    events = [e for e in store.batch_events(cur["batch"])]
    job = None
    if events:
        steps, fired = rules.plan(events, rules.DEFAULT_RULES, actions.ORDER)
        if steps:
            from procintel.jobs import store as jobs_store
            job = jobs_store.enqueue("pipeline_batch", f"{len(events)} changes detected", {"batch": cur["batch"]},
                                     dedupe=False, db_path=ctx.get("jobs_db"))
        for rule_id, n in fired.items():
            rule = next(r for r in rules.DEFAULT_RULES if r.id == rule_id)
            store.log_firing(cur["batch"], rule_id, n, list(rule.do), job)
    return {"batch": cur["batch"], "events": cur["counts"], "job": job}


def batch_steps(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    batch = params["batch"]
    cur = cursor or {"done": [], "derived": []}
    while True:
        events = store.batch_events(batch)  # includes the derived events logged so far
        plan, _ = rules.plan(events, rules.DEFAULT_RULES, actions.ORDER)
        last = max((actions.ORDER.index(a) for a in cur["done"]), default=-1)
        todo = [(a, keys) for a, keys in plan if a not in cur["done"] and actions.ORDER.index(a) > last]
        if not todo:
            return {"actions": cur["done"], "derived": sorted({e["type"] for e in cur["derived"]})}
        name, keys = todo[0]
        mine = {e["key"]: e for e in events if e["key"] in keys and not e["type"].startswith(DERIVED_PREFIXES)}
        new = [d for d in actions.ACTIONS[name].run(keys, mine, ctx) if d not in cur["derived"]]
        store.log_derived(batch, new)
        cur["derived"] += new
        cur["done"].append(name)
        yield cur
