"""Change detection (procintel.pipeline): what is tracked, recent events, the rules that fired, and running it now."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from procintel.api import access
from procintel.api.schemas import RuleSet
from procintel.jobs import store as jobs_store
from procintel.pipeline import actions, connector_config, connectors, entities, eventlog, rules, store

router = APIRouter()


@router.get("/pipeline")
def get_pipeline() -> dict:
    out = store.overview()
    out["entityTypes"] = [{"name": e.name, "every": str(e.every), "watched": e.watched}
                          for e in entities.ENTITY_TYPES.values()]
    out["rules"] = [rules.to_dict(r) for r in rules.active()]
    out["customised"] = rules.customised()
    out["eventTypes"] = rules.event_types(entities.ENTITY_TYPES)
    out["actions"] = [{"name": a.name, "label": a.label, "minHours": a.min_hours} for a in actions.ACTIONS.values()]
    return out


@router.get("/pipeline/connectors")
def get_connectors() -> dict:
    """Each source: mode, interval, cursor, last success, last error and failures in a row (it backs off)."""
    return {"connectors": connectors.status(), "backoffCap": connectors.words(connectors.BACKOFF_CAP)}


@router.put("/pipeline/connectors/{name}")
def put_connector(name: str, change: dict, request: Request) -> dict:
    """Change a source's mode, interval (everyHours) or on/off; equal to the defaults means reset."""
    if not access.is_admin_client(request):
        return access.refuse("changing a connector")
    try:
        connector_config.save(name, change)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return get_connectors()


@router.get("/pipeline/events")
def get_events(type: str | None = None, limit: int = 20, before: str | None = None) -> dict:
    """Batches of events newest first, with the rules they fired, the jobs queued and the actions run."""
    return eventlog.batches(type or None, max(1, min(limit, 100)), before)


@router.post("/pipeline/rules/dry-run")
def post_dry_run(req: RuleSet) -> dict:
    """What the given rules would have done on the last days' events; nothing is saved."""
    candidate = [rules.from_dict(r) for r in req.rules]
    errors = rules.validate(candidate, entities.ENTITY_TYPES, actions.ACTIONS)
    if errors:
        return JSONResponse({"error": "invalid rules", "detail": errors}, status_code=400)
    batches = store.recent_batches(entities.now() - rules.DRY_RUN_DAYS)
    return {"days": rules.DRY_RUN_DAYS.days, "candidate": rules.dry_run(candidate, batches, actions.ORDER),
            "current": rules.dry_run(rules.active(), batches, actions.ORDER)}


@router.put("/pipeline/rules")
def put_rules(req: RuleSet, request: Request) -> dict:
    if not access.is_admin_client(request):
        return access.refuse("changing pipeline rules")
    errors = rules.save([rules.from_dict(r) for r in req.rules], entities.ENTITY_TYPES, actions.ACTIONS)
    if errors:
        return JSONResponse({"error": "invalid rules", "detail": errors}, status_code=400)
    return get_pipeline()


@router.post("/pipeline/rules/reset")
def reset_rules(request: Request) -> dict:
    if not access.is_admin_client(request):
        return access.refuse("resetting pipeline rules")
    rules.reset()
    return get_pipeline()


@router.post("/pipeline/detect")
def post_detect(request: Request, types: str | None = None) -> dict:
    """Queue a detection run now, regardless of the intervals: every entity type, or ?types=Document,Notice."""
    if not access.is_admin_client(request):
        return access.refuse("starting change detection")
    chosen = [t for t in (types or "").split(",") if t]
    unknown = [t for t in chosen if t not in entities.ENTITY_TYPES]
    if unknown:
        return JSONResponse({"error": f"unknown entity types {unknown}"}, status_code=400)
    jid = jobs_store.enqueue("detect_changes", "requested from the Settings page",
                             {"force": True} | ({"types": chosen} if chosen else {}), dedupe=False)
    return {"queued": jid, "note": None if jid else "a detection run is already waiting or running"}
