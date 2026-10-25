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
  type: "str" | "url" | "json" | "int" | "float";
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
  precedents: Precedent[];
  /** empty when no description was given or embeddings are not configured */
  similarPackages: SimilarPackage[];
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
}

export interface JobsResponse {
  jobs: Job[];
  idleSeconds: number;
  runAfterIdleSeconds: number;
  running: string | null;
  workerOn: boolean;
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
