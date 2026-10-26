"""The Evaluation page (procintel.learning.overview): quality over time, comparisons, prediction models; queueing an
evaluation run; the labelling queue (procintel.learning.labelling). Promoting or discarding a shadow and activating a prompt use their own routes (shadows, prompts)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from procintel.api import access
from procintel.auth import service
from procintel.jobs import store as jobs_store
from procintel.learning import labelling, overview

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


class JudgeLabel(BaseModel):
    qid: str
    chunkId: str
    relevant: bool


class SentenceLabel(BaseModel):
    key: str
    supported: bool


class NewQuestion(BaseModel):
    question: str
    answerable: bool
    note: str | None = None


def _by(request: Request) -> str | None:
    user = getattr(request.state, "user", None)
    return service.pseudonym(user["username"]) if user else None


@router.get("/evaluation/labelling")
def get_labelling() -> dict:
    return labelling.queue()


@router.post("/evaluation/labels/judge")
def post_judge_label(req: JudgeLabel, request: Request) -> dict:
    try:
        labelling.label_judgment(req.qid, req.chunkId, req.relevant, _by(request))
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return labelling.queue()


@router.post("/evaluation/labels/sentence")
def post_sentence_label(req: SentenceLabel, request: Request) -> dict:
    try:
        labelling.label_sentence(req.key, req.supported, _by(request))
    except KeyError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    return labelling.queue()


@router.post("/evaluation/questions")
def post_question(req: NewQuestion) -> dict:
    try:
        row = labelling.add_question(req.question, req.answerable, req.note)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"added": row, **labelling.queue()}
