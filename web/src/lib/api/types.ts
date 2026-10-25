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

export interface RiskFlag {
  id: string;
  label: string;
  level: RiskLevel;
  /** "statistic" = computed from historical records; "model" = a model prediction (not built yet) */
  basis: "statistic" | "model";
  detail: string;
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

export interface FeedbackResponse {
  ok: boolean;
  feedbackId: string;
}

export interface AssessResponse {
  timeline: TimelineBenchmark | null;
  risks: RiskFlag[];
  governance: GovernanceScore[];
  precedents: Precedent[];
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
