// API contract shared by the mock routes (src/app/api/mock/*) and the future Python backend.
// Keep this file the single source of truth; the backend's response models should mirror it.

export type ProcGroup = "GO" | "CW" | "CS" | "NC";

export interface Country {
  code: string;
  name: string;
  region: string;
}

export interface Method {
  code: string;
  label: string;
  procGroups: ProcGroup[];
  n: number; // packages in the data using this method
}

export interface Options {
  countries: Country[];
  sectors: string[];
  procGroups: { code: ProcGroup; label: string }[];
  methods: Method[];
}

/** A quoted span from a source document. Every claim in a response must point at one of these. */
export interface Citation {
  id: string;
  docId: string;
  docType: string;
  title: string;
  section: string;
  quote: string;
  url: string;
  projectId: string;
  projectName: string;
  countryCode: string;
}

export interface AssessRequest {
  countryCode: string;
  procGroup: ProcGroup;
  methodCode: string;
  sector?: string;
  estimatedValueUsd?: number;
  description?: string;
  /** bid reference of the tender being planned; lets the pilot compare the prediction with the actual award time */
  tenderReference?: string;
}

export interface TimelineBenchmark {
  metric: "tender_to_award_days";
  /** which slice of history the numbers come from; falls back to wider slices when the narrow one is thin */
  scope: string;
  n: number;
  median: number;
  p25: number;
  p75: number;
  p90: number;
}

export type RiskLevel = "low" | "medium" | "high";

/** A record a risk flag rests on: a past package (linked to its award notice), a completion-report passage, or an indicator. */
export interface FlagEvidenceItem {
  kind: "package" | "report" | "indicator";
  ref: string;
  label: string;
  detail: string;
  url: string | null;
}

export interface RiskFlag {
  id: string;
  label: string;
  level: RiskLevel;
  /** "statistic" = computed from historical records; "model" = a gradient-boosted model estimate */
  basis: "statistic" | "model";
  detail: string;
  /** Records the flag rests on (empty for model flags and the mock engine) */
  evidence?: FlagEvidenceItem[];
  /** the tender stage it bites on ("all": across the timeline) */
  stage?: string | null;
}

/** A tender stage with its typical duration for comparable packages (null when the data has no dates for it). */
export interface Stage {
  key: string;
  label: string;
  median: number | null;
  p90: number | null;
  n: number;
  scope: string | null;
}

export interface GovernanceScore {
  indicator: string;
  year: number;
  value: number; // CPIA, 1 (low) to 6 (high)
}

export interface Precedent {
  citation: Citation;
  relevance: number; // 0..1
  matchedOn: string[];
  /** tender stage of the problem the passage describes */
  stage?: string | null;
}

export interface ResponseMeta {
  source: "mock" | "live";
  generatedAt: string;
  caveats: string[];
  /** id of this response in the server's log; feedback refers to it */
  responseId: string;
}

export type FeedbackRating = "useful" | "not_useful" | "bad_citation";

export interface FeedbackRequest {
  responseId: string;
  rating: FeedbackRating;
  /** required for "bad_citation": the id of a citation shown in that response */
  citationId?: string;
  comment?: string;
}

/** A backend setting shown on the configuration page. API keys are never included. */
export interface ConfigSetting {
  key: string;
  label: string;
  group: string;
  type: "str" | "url" | "json" | "int" | "float" | "date";
  value: string | number;
  /** value when the backend started */
  default: string | number;
  editable: boolean;
  note: string;
  min: number | null;
  max: number | null;
}

export interface ConfigResponse {
  settings: ConfigSetting[];
}

export interface ConfigUpdate {
  values: Record<string, string | number>;
  /** also write data/config.json so the values survive a restart */
  save?: boolean;
}

/** A named set of settings saved on the backend (data/config_profiles.json). */
export interface ConfigProfile {
  name: string;
  values: Record<string, string | number>;
  /** the settings whose value differs from the startup value */
  differs: Record<string, string | number>;
}

/** Search quality over the evaluation questions (no answers generated). */
export interface RetrievalMetrics {
  bm25_p5: number;
  hybrid_p5: number;
  bm25_r10: number;
  hybrid_r10: number;
  questions: number;
}

export interface CompareResponse {
  before: RetrievalMetrics;
  after: RetrievalMetrics;
}

export interface FeedbackResponse {
  ok: boolean;
  feedbackId: string;
}

/** A past awarded contract whose description is close to the planned package's. */
export interface SimilarPackage {
  packageId: string;
  projectId: string;
  projectName: string;
  countryCode: string;
  method: string;
  description: string;
  /** null when the tender or award date is not in the data */
  tenderToAwardDays: number | null;
  valueUsd: number | null;
  /** the package was re-tendered (procintel.rebid evidence) */
  rebid: boolean;
}

export interface AssessResponse {
  timeline: TimelineBenchmark | null;
  risks: RiskFlag[];
  governance: GovernanceScore[];
  /** Worldwide Governance Indicators (estimate, 0 = world average, about -2.5 to +2.5); filled where CPIA is missing */
  wgi?: GovernanceScore[];
  precedents: Precedent[];
  /** empty when no description was given or embeddings are not configured */
  similarPackages: SimilarPackage[];
  /** tender stages with typical durations, for the stage timeline */
  stages?: Stage[];
  /** the award time this assessment predicts, kept in the log for later comparison */
  prediction?: { basis: "model" | "historical median"; days_p50: number; days_p90: number | null; p_long: number | null } | null;
  meta: ResponseMeta;
}

export interface AskRequest {
  question: string;
  countryCode?: string;
  procGroup?: ProcGroup;
}

/** One sentence of the answer and the citations (indices into `citations`) that support it. */
export interface AnswerSentence {
  text: string;
  citations: number[];
}

export interface AskResponse {
  answer: AnswerSentence[];
  citations: Citation[];
  /** true when the sources did not support an answer; the UI must say so rather than show a guess */
  unsupported: boolean;
  meta: ResponseMeta;
}

/** A background job (procintel.jobs): runs only after the app has been idle for a while. */
export interface Job {
  id: string;
  kind: "drift_check" | "retrain" | "refresh" | string;
  reason: string;
  status: "pending" | "running" | "done" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
  steps: number;
  /** high runs first; a running job pauses between steps when a higher one waits */
  priority: JobPriority;
  worker: string | null;
}

export type JobPriority = "high" | "normal" | "background";

export interface JobsResponse {
  jobs: Job[];
  /** default priority of each job kind */
  kinds: Record<string, JobPriority>;
  idleSeconds: number;
  runAfterIdleSeconds: number;
  running: string | null;
  workerOn: boolean;
  /** thread: worker inside the backend; external: separate worker processes; off */
  workerMode: "thread" | "external" | "off";
  /** data version this backend has loaded (external mode) */
  dataVersion: string | null;
}

/** Something user feedback asks a person to look at (built by the feedback_review job). */
export interface ReviewItem {
  kind: "flagged_citation" | "refused_question" | "not_useful";
  key: string;
  responses: number;
  questions: string[];
  comments: string[];
}

export interface FeedbackReviewResponse {
  items: ReviewItem[];
  /** passages search moves to the end of its results */
  demoted: string[];
  demoteAfter: number;
}

/** Search quality on the evaluation questions (procintel.learning.evaluate.retrieval_metrics). */
export interface RetrievalScores {
  bm25_p5: number;
  hybrid_p5: number;
  bm25_r10: number;
  hybrid_r10: number;
  questions: number;
}

/** An alternative index built next to the live one; promoted only after its evaluation (GET /shadows). */
export interface ShadowBuild {
  name: string;
  label: string;
  status: "building" | "built" | "evaluated" | "promoted" | "discarded";
  built_at: string | null;
  evaluated_at: string | null;
  metrics: { live: RetrievalScores; shadow: RetrievalScores; passages: { live: number; shadow: number } } | null;
  note: string | null;
}

export interface ShadowsResponse {
  shadows: ShadowBuild[];
  available: { name: string; label: string }[];
}

/** One evaluation run (eval/history.jsonl); measures absent when the run did not include them. */
export interface EvalRun {
  time: string;
  judged_pairs?: number;
  bm25_p5?: number;
  hybrid_p5?: number;
  bm25_r10?: number;
  hybrid_r10?: number;
  gate_prec?: number | null;
  answered?: number;
  answerable?: number;
  supported_sentences?: number;
  sentences?: number;
  supported_independent?: number;
  independent_judge?: string;
  refused_traps?: number;
  traps?: number;
  median_seconds?: number;
  note?: string;
  changesBefore?: { at: string; what: string; detail: string }[];
}

export interface ModelRetrain {
  trained_at: string;
  n: number | null;
  projects?: number;
  folds?: number;
  /** per metric: [model, baseline] from project-grouped cross-validation */
  metrics: Record<string, [number, number] | null>;
  use?: Record<string, boolean>;
  source?: string;
}

/** The labelling queue (GET /evaluation/labelling). */
export interface LabellingQueue {
  judge: {
    items: { qid: string; question: string; chunkId: string; passage: string | null; judge: boolean; judgeModel: string | null }[];
    agreement: { agree: number; labelled: number };
  };
  sentences: {
    items: { key: string; qid: string; sentence: string; passages: Record<string, string>; answerModel: boolean; independent: boolean }[];
    sentences: number;
    disagreements: number;
    decided: { answerModel: number; independent: number; labelled: number };
  };
  questions: { kind: "refused_question" | "not_useful"; question: string; responses: number; comments: string[]; inSet: boolean }[];
}

/** The Evaluation page (GET /evaluation). */
export interface EvaluationResponse {
  quality: EvalRun[];
  comparisons: {
    shadows: ShadowBuild[];
    shadowKinds: { name: string; label: string }[];
    prompts: { name: string; label: string; active: number; version: number; note: string | null;
      evaluation: { versions: { active: number; candidate: number }; active: PromptEvalSide; candidate: PromptEvalSide } }[];
    models: { name: string; run: EvalRun; live: EvalRun | null }[];
  };
  models: {
    retrains: ModelRetrain[];
    driftChecks: { at: string; retrain?: boolean; why?: string; new_packages?: number; mae_new?: number | null; mae_cv?: number }[];
  };
}

/** One side of a prompt evaluation (procintel.learning.prompt_eval). */
export interface PromptEvalSide {
  answered: number;
  answerable: number;
  supported_sentences: number;
  sentences: number;
  refused_traps: number;
  traps: number;
  median_seconds: number | null;
}

export interface PromptVersion {
  version: number; // 0 = the default shipped with the code
  text: string;
  active: boolean;
  created: string | null;
  note: string | null;
  activated: string | null;
  evaluation: { versions: { active: number; candidate: number }; questions: number; active: PromptEvalSide; candidate: PromptEvalSide } | null;
}

/** A prompt sent to a model (GET /prompts). */
export interface PromptInfo {
  name: string;
  label: string;
  usedBy: string;
  /** "answers": a new version is compared with the active one on sample questions before activation */
  evaluatedBy: "answers" | null;
  active: number;
  versions: PromptVersion[];
}

/** Change detection (GET /pipeline): tracked entities, recent events and rule firings. */
export interface PipelineResponse {
  tracked: Record<string, number>;
  lastRun: Record<string, { ranAt: string; items: number; events: number; note: string }>;
  events: { type: string; key: string; changed: string[]; detectedAt: string; batch: string }[];
  firings: { batch: string; rule: string; events: number; actions: string[]; job: string | null; firedAt: string }[];
  entityTypes: { name: string; every: string; watched: string[] }[];
  rules: PipelineRule[];
  /** false while the default rules are in use */
  customised: boolean;
  eventTypes: string[];
  actions: { name: string; label: string; minHours: number }[];
}

/** A source connector (GET /pipeline/connectors). */
export interface Connector {
  name: string;
  source: string;
  mode: "poll" | "push" | "subscribe" | "upload";
  every: string;
  /** what the next read asks for, in words */
  cursor: string;
  lastRead: string | null;
  lastSuccess: { at: string; items: number; events: number; note: string } | null;
  lastError: { at: string; message: string } | null;
  /** failed reads in a row; the source backs off while this is above 1 */
  failures: number;
  nextRead: string | null;
  /** the interval has passed: read on the next detection run (which waits for idle time) */
  due: boolean;
}

export interface ConnectorsResponse {
  connectors: Connector[];
  backoffCap: string;
}

/** One detection batch in the event log (GET /pipeline/events). */
export interface EventBatch {
  batch: string;
  at: string;
  counts: Record<string, number>;
  events: { type: string; key: string; changed: string[]; at: string }[];
  firings: { rule: string; events: number; actions: string[]; job: string | null; at: string;
    jobStatus: { kind: string; status: string; finishedAt: string | null; error: string | null } | null }[];
  actionsRun: { action: string; outcome: string; at: string }[];
}

export interface EventLogResponse {
  batches: EventBatch[];
  types: string[];
  more: boolean;
}

/** An uploaded file and how far it got (GET /intake/uploads). */
export interface Upload {
  upload_id: string;
  filename: string;
  format: string;
  size: number;
  uploaded_at: string;
  /** received → extracted → classified → linked → added | kept; or needs_review, failed, duplicate */
  status: string;
  stages: { stage: string; at: string; detail: string }[];
  doc_type: string | null;
  type_confidence: number | null;
  links: { projects: { id: string; name: string | null; country: string | null; known: boolean }[]; countries: string[] } | null;
  doc_id: string | null;
  error: string | null;
}

export interface UploadsResponse {
  uploads: Upload[];
  formats: string[];
  maxMb: number;
}

export interface PipelineRule {
  id: string;
  on: string[];
  /** for .changed events: fire only when one of these fields changed */
  fields: string[];
  do: string[];
  enabled: boolean;
}

export interface DryRunSide {
  batches: number;
  events: number;
  fired: Record<string, number>;
  actions: Record<string, { events: number; runs: number }>;
}

export interface DryRunResponse {
  days: number;
  candidate: DryRunSide;
  current: DryRunSide;
}

/** The signed-in user (GET /auth/me). mode "off": sign-in disabled, everyone is an admin. */
export interface AuthUser {
  username: string;
  role: "planner" | "admin";
  mode: "local" | "off";
}

/** An account (GET /auth/users, admins). */
export interface Account {
  username: string;
  role: "planner" | "admin";
  active: boolean;
  createdAt: string | null;
  lastLogin: string | null;
}

/** Home dashboard (GET /dashboard and friends; procintel.insights.dashboard). */
export interface DashMeasure {
  key: string;
  label: string;
  unit: "days" | "share" | "per project";
  level: "package" | "project";
  higherIsWorse: boolean;
  note: string;
  groups?: string[];
}

export interface DashboardResponse {
  summary: { projects: number; countries: number; packages: number; awarded: number; median_days: number | null; long_share: number | null; rebid_projects: number; amendment_projects: number };
  measures: DashMeasure[];
  groups: Record<string, string>;
  trends: {
    award: { year: number; median_days: number; long_share: number; n: number; incomplete: boolean }[];
    problems: { year: number; per_project: number; projects: number }[];
    completeUntil: number;
    note: string;
  };
  problemMix: { kinds: { kind: string; passages: number }[]; note: string };
  fewProjects: number;
}

export interface RankingRow { key: string; label: string; value: number; n: number; projects: number; few: boolean }
export interface RankingResponse { measure: DashMeasure; group: string; groupLabel: string; rows: RankingRow[] }
export interface HeatmapResponse {
  measure: DashMeasure;
  minN: number;
  cells: { country: string; countryLabel: string; method: string; value: number; n: number }[];
}
export type DashRecords =
  | { kind: "packages"; records: { packageId: string; projectId: string; method: string; description: string; days: number; tenderStart: string | null; url: string }[] }
  | { kind: "projects"; records: { projectId: string; name: string; country: string; rebid: boolean; amendment: boolean; procurementBelowSatisfactory: boolean | null; problemPassages: number | null; url: string }[] };
