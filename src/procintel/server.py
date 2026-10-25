"""HTTP API for the web app. Response models mirror web/src/lib/api/types.ts; keep the two in step.

    uvicorn procintel.server:app --port 8000        (with PYTHONPATH=src)
    then run the web app with NEXT_PUBLIC_API_BASE=http://localhost:8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal

import duckdb
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from procintel import config, evidence, feedback, predict, rebid, stats
from procintel.answer import ask as run_ask, idf
from procintel.flag_evidence import FlagEvidence
from procintel.assess import assess as run_assess
from procintel.retrieve import DB_PATH, Retriever
from procintel.similar import Similar

ProcGroup = Literal["GO", "CW", "CS", "NC"]


class Country(BaseModel):
    code: str
    name: str
    region: str


class Method(BaseModel):
    code: str
    label: str
    procGroups: list[ProcGroup]
    n: int


class ProcGroupOption(BaseModel):
    code: ProcGroup
    label: str


class Options(BaseModel):
    countries: list[Country]
    sectors: list[str]
    procGroups: list[ProcGroupOption]
    methods: list[Method]


class Citation(BaseModel):
    id: str
    docId: str
    docType: str
    title: str
    section: str
    quote: str
    url: str
    projectId: str
    projectName: str
    countryCode: str


class AssessRequest(BaseModel):
    countryCode: str = Field(min_length=2)
    procGroup: ProcGroup
    methodCode: str = Field(min_length=1)
    sector: str | None = None
    estimatedValueUsd: float | None = None
    description: str | None = Field(default=None, max_length=2000)


class TimelineBenchmark(BaseModel):
    metric: Literal["tender_to_award_days"]
    scope: str
    n: int
    median: float
    p25: float
    p75: float
    p90: float


class FlagEvidenceItem(BaseModel):
    kind: Literal["package", "report", "indicator"]
    ref: str
    label: str
    detail: str
    url: str | None = None


class RiskFlag(BaseModel):
    id: str
    label: str
    level: Literal["low", "medium", "high"]
    basis: Literal["statistic", "model"]
    detail: str
    evidence: list[FlagEvidenceItem] = []


class GovernanceScore(BaseModel):
    indicator: str
    year: int
    value: float


class Precedent(BaseModel):
    citation: Citation
    relevance: float
    matchedOn: list[str]


class ResponseMeta(BaseModel):
    source: Literal["mock", "live"]
    generatedAt: str
    caveats: list[str]
    responseId: str  # used to attach feedback to exactly this response


class SimilarPackage(BaseModel):
    packageId: str
    projectId: str
    projectName: str
    countryCode: str
    method: str
    description: str
    tenderToAwardDays: int | None
    valueUsd: int | None
    rebid: bool


class AssessResponse(BaseModel):
    timeline: TimelineBenchmark | None
    risks: list[RiskFlag]
    governance: list[GovernanceScore]
    precedents: list[Precedent]
    similarPackages: list[SimilarPackage] = []
    meta: ResponseMeta


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    countryCode: str | None = None
    procGroup: ProcGroup | None = None


class AnswerSentence(BaseModel):
    text: str
    citations: list[int]


class AskResponse(BaseModel):
    answer: list[AnswerSentence]
    citations: list[Citation]
    unsupported: bool
    meta: ResponseMeta


class State:
    """Everything derived from the database, loaded once at startup."""

    def __init__(self, db_path: Path):
        con = duckdb.connect(str(db_path), read_only=True)
        self.options = stats.options(con)
        self.bench = stats.benchmarks(con)
        self.governance = stats.governance(con)
        self.rebid = rebid.by_country(con)
        self.rebid_cost = rebid.cost(con)
        self.amendments = evidence.by_country(con, "amendment")
        self.similar = Similar(db_path)
        self.flag_evidence = FlagEvidence(db_path)
        con.close()
        self.retriever = Retriever(db_path)
        idf(self.retriever)  # term weights for picking answer sentences
        self.timeline_model = predict.load()  # None until `python -m procintel.predict` has been run
        self.region = {c["code"]: c["region"] for c in self.options["countries"]}
        self.country_name = {c["code"]: c["name"] for c in self.options["countries"]}


@lru_cache(maxsize=1)
def state(db_path: Path = DB_PATH) -> State:
    return State(db_path)


@asynccontextmanager
async def lifespan(_: FastAPI):
    for key, err in config.load_saved().items():  # saved settings from the configuration page
        print(f"config: saved value for {key} ignored: {err}")
    state()  # build the index before the first request rather than during it
    yield


app = FastAPI(title="procintel", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3100", "http://127.0.0.1:3100"],
                   allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"])


@app.exception_handler(RequestValidationError)
async def bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    # 400 like the mock routes; the client only checks res.ok
    errors = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse({"error": "invalid request", "detail": errors}, status_code=400)


@app.get("/options", response_model=Options)
def get_options() -> dict:
    return state().options


@app.post("/assess", response_model=AssessResponse)
def post_assess(req: AssessRequest) -> dict:
    s = state()
    body = req.model_dump()
    out = run_assess(s.retriever, s.bench, s.governance, body, s.timeline_model, s.region.get(body["countryCode"]),
                     s.country_name.get(body["countryCode"], ""), s.rebid, s.rebid_cost, s.amendments)
    s.flag_evidence.attach(out["risks"], body, s.bench, out["timeline"], out["governance"])
    try:
        out["similarPackages"] = s.similar.search(body.get("description") or "", body["procGroup"])
    except Exception:  # embedding server down: the assessment stands without this section
        out["similarPackages"] = []
    feedback.log_response("assess", body, out)
    return out


@app.post("/ask", response_model=AskResponse)
def post_ask(req: AskRequest) -> dict:
    out = run_ask(state().retriever, req.question, req.countryCode, req.procGroup)
    feedback.log_response("ask", req.model_dump(), out)
    return out


class FeedbackRequest(BaseModel):
    responseId: str = Field(min_length=1, max_length=64)
    rating: Literal["useful", "not_useful", "bad_citation"]
    citationId: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    ok: bool
    feedbackId: str


@app.post("/feedback", response_model=FeedbackResponse)
def post_feedback(req: FeedbackRequest) -> dict:
    try:
        fid = feedback.add(req.responseId, req.rating, req.citationId, req.comment)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return {"ok": True, "feedbackId": fid}


class ConfigSetting(BaseModel):
    key: str
    label: str
    group: str
    type: Literal["str", "url", "json", "int", "float"]
    value: str | int | float
    default: str | int | float
    editable: bool
    note: str
    min: float | None
    max: float | None


class ConfigResponse(BaseModel):
    settings: list[ConfigSetting]


class ConfigUpdate(BaseModel):
    values: dict[str, str | int | float]
    save: bool = False


@app.get("/config", response_model=ConfigResponse)
def get_config() -> dict:
    return {"settings": config.listing()}


@app.put("/config", response_model=ConfigResponse)
def put_config(req: ConfigUpdate) -> dict:
    errors = config.update(req.values, save=req.save)
    if errors:
        return JSONResponse({"error": "invalid settings", "detail": errors}, status_code=400)
    return {"settings": config.listing()}


@app.get("/health")
def health() -> dict:
    return {"ok": True}
