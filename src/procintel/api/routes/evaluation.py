"""The Evaluation page (procintel.learning.overview): quality over time, comparisons, prediction models; queueing an
evaluation run. Promoting or discarding a shadow and activating a prompt use their own routes (shadows, prompts)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from procintel.api import access
from procintel.jobs import store as jobs_store
from procintel.learning import overview

router = APIRouter()


class EvaluationRun(BaseModel):
    answers: bool = False   # False: search quality only (a minute); True: answers too (about 10 minutes)


@router.get("/evaluation")
def get_evaluation() -> dict:
    return overview.page()


@router.post("/evaluation/run")
def post_run(req: EvaluationRun, request: Request) -> dict:
    if not access.is_admin_client(request):
        return access.refuse("starting an evaluation")
    what = "full evaluation (search and answers)" if req.answers else "search-quality evaluation"
    jid = jobs_store.enqueue("evaluate", f"{what}, requested", {"answers": req.answers})
    return {"queued": jid, "note": None if jid else "an evaluation is already waiting or running"}
