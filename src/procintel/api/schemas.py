"""Request and response models. They mirror web/src/lib/api/types.ts; keep the two in step."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
    # optional bid / contract reference of the tender being planned, so the pilot can compare the prediction with the
    # actual award time when the award notice is published (docs/pilot-plan.md)
    tenderReference: str | None = Field(default=None, max_length=120)
    # the tracked project the package belongs to, if any: its approval date and size sharpen the model
    projectId: str | None = Field(default=None, max_length=20)
    # False: the forecast and risks without the past-experience passages, whose selection takes a model call (about 15 s
    # a package). The planning page shows no passages, so it asks without them.
    withPrecedents: bool = True


class GoalRequest(AssessRequest):
    targetDays: int = Field(ge=7, le=2000)   # awarded within this many days of the tender notice
    maxLots: int = Field(default=4, ge=1, le=10)


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


class Stage(BaseModel):
    key: str
    label: str
    median: float | None  # typical days for comparable packages (None: the data has no dates for this stage)
    p90: float | None
    n: int
    scope: str | None


class RiskFlag(BaseModel):
    id: str
    label: str
    level: Literal["low", "medium", "high"]
    basis: Literal["statistic", "model"]
    detail: str
    evidence: list[FlagEvidenceItem] = []
    stage: str | None = None  # the tender stage it bites on ("all": across the timeline)


class GovernanceScore(BaseModel):
    indicator: str
    year: int
    value: float


class Precedent(BaseModel):
    citation: Citation
    relevance: float
    matchedOn: list[str]
    stage: str | None = None  # tender stage of the problem it describes (procintel.prediction.stages)


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


class Prediction(BaseModel):
    basis: Literal["model", "historical median"]
    days_p50: int
    days_p90: int | None = None
    p90_basis: Literal["model", "historical"] | None = None   # the model's slow case only where it beat the baseline
    p_long: float | None = None


class AssessResponse(BaseModel):
    timeline: TimelineBenchmark | None
    risks: list[RiskFlag]
    governance: list[GovernanceScore]
    wgi: list[GovernanceScore] = []  # Worldwide Governance Indicators, shown where CPIA is missing
    precedents: list[Precedent]
    similarPackages: list[SimilarPackage] = []
    prediction: Prediction | None = None
    stages: list[Stage] = []  # tender stages with typical durations, for the timeline
    meta: ResponseMeta


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    countryCode: str | None = None
    procGroup: ProcGroup | None = None


class AnswerSentence(BaseModel):
    text: str
    citations: list[int]


class AskFallback(BaseModel):
    """What to show when nothing answers the question directly: what was searched and what the closest passages say."""
    answer: list[AnswerSentence]
    citations: list[Citation]


class AskResponse(BaseModel):
    answer: list[AnswerSentence]
    citations: list[Citation]
    unsupported: bool
    fallback: AskFallback | None = None
    meta: ResponseMeta


class FeedbackRequest(BaseModel):
    responseId: str = Field(min_length=1, max_length=64)
    rating: Literal["useful", "not_useful", "bad_citation"]
    citationId: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(BaseModel):
    ok: bool
    feedbackId: str


class ConfigSetting(BaseModel):
    key: str
    label: str
    group: str
    type: Literal["str", "url", "json", "int", "float", "date"]
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


class ProfileSave(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class ProfileApply(BaseModel):
    save: bool = False


class CompareRequest(BaseModel):
    values: dict[str, str | int | float]


class JobRequest(BaseModel):
    kind: Literal["drift_check", "retrain", "refresh", "feedback_review"]
    reason: str = Field(default="queued from the Settings page", max_length=200)
    priority: Literal["high", "normal", "background"] | None = None  # default: the kind's registered priority


class PromptSave(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    note: str = Field(default="", max_length=300)


class PromptActivate(BaseModel):
    version: int = Field(ge=0)


class RuleSet(BaseModel):
    rules: list[dict] = Field(max_length=200)  # [{id, on, fields, do, enabled}], validated by procintel.pipeline.rules


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


class NewUser(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)
    role: Literal["planner", "reviewer", "admin"] = "planner"


class UserUpdate(BaseModel):
    role: Literal["planner", "reviewer", "admin"] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, max_length=200)


# --- planning assistant (procintel.assistant): the conversation and the plan live in the browser, each call carries both ---

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatPackage(BaseModel):
    id: str = Field(max_length=20)
    name: str = Field(max_length=80)
    procGroup: ProcGroup
    methodCode: str = Field(max_length=10)
    sector: str | None = None
    estimatedValueUsd: float | None = None
    description: str | None = Field(default=None, max_length=2000)
    tenderStart: str | None = None
    after: str | None = None


class ChatPlan(BaseModel):
    countryCode: str | None = None
    projectStart: str | None = None
    deadline: str | None = None
    packages: list[ChatPackage] = Field(default_factory=list, max_length=12)


class SummarizeRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=60)


class PlanChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=60)   # ends with the planner's latest message
    plan: ChatPlan = Field(default_factory=ChatPlan)
    results: str = Field(default="", max_length=4000)                    # the plan's forecast, as text, for questions about it
