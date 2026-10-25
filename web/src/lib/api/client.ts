import type {
  AskRequest,
  AskResponse,
  AssessRequest,
  AssessResponse,
  CompareResponse,
  ConfigProfile,
  ConfigResponse,
  ConfigUpdate,
  FeedbackRequest,
  FeedbackReviewResponse,
  JobsResponse,
  FeedbackResponse,
  Options,
} from "./types";

// Default is the in-app mock. Point at the Python backend with NEXT_PUBLIC_API_BASE=http://localhost:8000
// (inlined at build time, so restart `next dev` after changing it).
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/mock";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status} ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  options: () => call<Options>("/options"),
  assess: (req: AssessRequest) => call<AssessResponse>("/assess", { method: "POST", body: JSON.stringify(req) }),
  ask: (req: AskRequest) => call<AskResponse>("/ask", { method: "POST", body: JSON.stringify(req) }),
  feedback: (req: FeedbackRequest) => call<FeedbackResponse>("/feedback", { method: "POST", body: JSON.stringify(req) }),
  config: () => call<ConfigResponse>("/config"),
  /** Per-setting errors come back as { errors } instead of an exception, so the form can show them in place. */
  updateConfig: async (req: ConfigUpdate): Promise<{ settings: ConfigResponse["settings"] } | { errors: Record<string, string> }> => {
    const res = await fetch(`${API_BASE}/config`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    const body = await res.json().catch(() => ({}));
    if (res.ok) return { settings: body.settings };
    if (res.status === 400 && body.detail && typeof body.detail === "object" && !Array.isArray(body.detail)) return { errors: body.detail };
    throw new Error(`PUT /config failed: ${res.status}`);
  },
  profiles: () => call<{ profiles: ConfigProfile[] }>("/config/profiles"),
  saveProfile: (name: string) => call<{ profiles: ConfigProfile[] }>("/config/profiles", { method: "POST", body: JSON.stringify({ name }) }),
  applyProfile: (name: string, save: boolean) =>
    call<ConfigResponse>(`/config/profiles/${encodeURIComponent(name)}/apply`, { method: "POST", body: JSON.stringify({ save }) }),
  deleteProfile: (name: string) => call<{ profiles: ConfigProfile[] }>(`/config/profiles/${encodeURIComponent(name)}`, { method: "DELETE" }),
  /** search quality under the current settings and under the given values; the values are not applied */
  compare: (values: Record<string, string | number>) => call<CompareResponse>("/config/compare", { method: "POST", body: JSON.stringify({ values }) }),
  jobs: () => call<JobsResponse>("/jobs"),
  feedbackReview: () => call<FeedbackReviewResponse>("/feedback/review"),
  queueJob: (kind: string) =>
    call<{ queued: string | null; note: string | null }>("/jobs", { method: "POST", body: JSON.stringify({ kind, reason: "queued from the Settings page" }) }),
};
