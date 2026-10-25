"""Change detection (procintel.pipeline): what is tracked, recent events, the rules that fired, and running it now."""
from __future__ import annotations

from fastapi import APIRouter, Request

from procintel.api import access
from procintel.jobs import store as jobs_store
from procintel.pipeline import actions, entities, rules, store

router = APIRouter()


@router.get("/pipeline")
def get_pipeline() -> dict:
    out = store.overview()
    out["entityTypes"] = [{"name": e.name, "every": str(e.every), "watched": e.watched}
                          for e in entities.ENTITY_TYPES.values()]
    out["rules"] = [{"id": r.id, "on": list(r.on), "fields": list(r.fields), "do": list(r.do), "enabled": r.enabled}
                    for r in rules.DEFAULT_RULES]
    out["actions"] = [{"name": a.name, "label": a.label} for a in actions.ACTIONS.values()]
    return out


@router.post("/pipeline/detect")
def post_detect(request: Request) -> dict:
    """Queue a detection run over every entity type now, regardless of their intervals."""
    if not access.is_admin_client(request):
        return access.refuse("starting change detection")
    jid = jobs_store.enqueue("detect_changes", "requested from the Settings page", {"force": True})
    return {"queued": jid, "note": None if jid else "a detection run is already waiting or running"}
