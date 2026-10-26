"""Change detection and batch execution, as two job kinds on the existing queue (procintel.jobs).

detect_changes (normal priority, queued hourly): for every entity type whose interval has passed (longer after failed
reads, procintel.pipeline.connectors), read the source,
compare with the stored state and record the events; a type seen for the first time is seeded from the database
without events. Then the default rules turn the batch's events into a plan, and one pipeline_batch job is queued.

pipeline_batch (normal priority): runs the plan's actions one per job step (so it pauses when the app is used), adds
the derived events they report (Package.award_changed, Data.updated) to the batch, and plans again: an action is
asked for at most once per batch, and only actions later in the registry order can be added, so a batch cannot loop.
"""
from __future__ import annotations

from typing import Iterator

from procintel.pipeline import actions, connectors, entities, rules, store

DERIVED_PREFIXES = ("Package.", "Data.", "Documents.", "Passages.", "Upload.")


def _context(name: str) -> dict:
    if name == "Document":
        return {"tracked": list(store.states("Document"))}
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
        if connectors.due(et, params.get("force", False)):
            known = store.states(name)
            seed = et.read_db() if not known else {}
            if seed:   # first run: start from what the database holds, without events
                n = store.seed(name, et.watched, seed)
                store.log_detection(cur["batch"], name, n, 0, "first run: state seeded from the database")
                cur["counts"][name] = 0
            else:      # tracked before, or new to the database too: everything the source has is new
                try:
                    rows, complete = et.read_source(_context(name))
                except Exception as e:  # a failing source is logged and backs off; the other sources go on
                    store.log_detection(cur["batch"], name, 0, 0, error=f"{type(e).__name__}: {e}"[:500])
                    cur["done"].append(name)
                    yield cur
                    continue
                events = store.diff(name, et.watched, rows, known, complete)
                store.record(name, cur["batch"], events, list(rows))
                store.log_detection(cur["batch"], name, len(rows), len(events),
                                    "" if complete else "newest items only (no removals from a partial read)")
                cur["counts"][name] = len(events)
        cur["done"].append(name)
        yield cur
    job = queue_batch(cur["batch"], "changes detected", ctx.get("jobs_db"))
    return {"batch": cur["batch"], "events": cur["counts"], "job": job}


def queue_batch(batch: str, why: str, jobs_db=None, priority: str | None = None) -> str | None:
    """Plan a batch's logged events with the active rules, queue one pipeline_batch job when any action is asked
    for, and log which rules fired. Returns the job id (None: nothing to do)."""
    events = store.batch_events(batch)
    if not events:
        return None
    steps, fired = rules.plan(events, rules.active(), actions.ORDER)
    job = None
    if steps:
        from procintel.jobs import store as jobs_store
        job = jobs_store.enqueue("pipeline_batch", f"{len(events)} {why}", {"batch": batch}, dedupe=False,
                                 db_path=jobs_db, priority=priority)
    for rule_id, n in fired.items():
        rule = next(r for r in rules.active() if r.id == rule_id)
        store.log_firing(batch, rule_id, n, list(rule.do), job)
    return job


def batch_steps(params: dict, cursor: dict | None, ctx: dict) -> Iterator[dict]:
    batch = params["batch"]
    cur = cursor or {"done": [], "derived": []}
    while True:
        events = store.batch_events(batch)  # includes the derived events logged so far
        plan, _ = rules.plan(events, rules.active(), actions.ORDER)
        last = max((actions.ORDER.index(a) for a in cur["done"]), default=-1)
        todo = [(a, keys) for a, keys in plan if a not in cur["done"] and actions.ORDER.index(a) > last]
        if not todo:
            return {"actions": cur["done"], "derived": sorted({e["type"] for e in cur["derived"]})}
        name, keys = todo[0]
        action = actions.ACTIONS[name]
        since = store.hours_since_action(name) if action.min_hours else None
        if since is not None and since < action.min_hours:  # costly action that ran recently: skip, and say so
            store.log_action(batch, name, f"skipped: ran {since:.1f} h ago (at most every {action.min_hours:g} h)")
        else:
            mine = {e["key"]: e for e in events if e["key"] in keys and not e["type"].startswith(DERIVED_PREFIXES)}
            new = [d for d in action.run(keys, mine, ctx) if d not in cur["derived"]]
            store.log_derived(batch, new)
            store.log_action(batch, name, "ran")
            cur["derived"] += new
        cur["done"].append(name)
        yield cur


def reconcile() -> dict[str, int]:
    """After a full refresh: bring the state of every tracked type in line with the database and log the differences
    as events of their own batch, without queuing actions (the refresh already did the work). Types not tracked yet
    are left for their first detection run. Returns the events per type."""
    batch = "refresh-" + store.new_batch()
    out = {}
    for name, et in entities.ENTITY_TYPES.items():
        known = store.states(name)
        if not known:
            continue
        rows = et.read_db()
        events = store.diff(name, et.watched, rows, known, complete=True)
        store.record(name, batch, events, list(rows))
        store.log_detection(batch, name, len(rows), len(events), "reconciled with the database after a full refresh")
        out[name] = len(events)
    return out
