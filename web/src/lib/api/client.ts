import type {
  DashboardResponse,
  DashRecords,
  HeatmapResponse,
  RankingResponse,
  Account,
  AuthUser,
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
  DryRunResponse,
  ConnectorsResponse,
  EventLogResponse,
  Upload,
  UploadsResponse,
  Options,
  PipelineResponse,
  PipelineRule,
  PromptInfo,
  ShadowsResponse,
} from "./types";

// Calls go to this app's own server, which forwards them to the backend named by API_URL (read per request, so the
// built app is not tied to one backend; see src/app/api/backend). Without API_URL the in-app mock answers.
export const API_BASE = "/api/backend";
export const SIGNED_OUT = "procintel:signed-out";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event(SIGNED_OUT)); // the session ended: AuthProvider re-checks and shows the sign-in page
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status} ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

/** POST/PATCH whose 400 answer is an error message the form shows in place. */
async function send<T>(path: string, method: string, body: unknown): Promise<T | { error: string }> {
  const res = await fetch(`${API_BASE}${path}`, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const out = await res.json().catch(() => ({}));
  if (res.ok) return out as T;
  if (res.status === 400 || res.status === 401 || res.status === 429) return { error: out.error ?? `failed (${res.status})` };
  throw new Error(`${method} ${path} failed: ${res.status}`);
}

export const api = {
  /** null when not signed in */
  dashboard: () => call<DashboardResponse>("/dashboard"),
  ranking: (measure: string, group: string) => call<RankingResponse>(`/dashboard/ranking?measure=${measure}&group=${group}`),
  heatmap: (measure: string) => call<HeatmapResponse>(`/dashboard/heatmap?measure=${measure}`),
  records: (group: string, key: string, measure: string, method?: string) =>
    call<DashRecords>(`/dashboard/records?group=${group}&key=${encodeURIComponent(key)}&measure=${measure}${method ? `&method=${encodeURIComponent(method)}` : ""}`),
  me: async (): Promise<AuthUser | null> => {
    const res = await fetch(`${API_BASE}/auth/me`);
    return res.ok ? ((await res.json()) as AuthUser) : null;
  },
  login: (username: string, password: string) => send<AuthUser>("/auth/login", "POST", { username, password }),
  logout: () => call<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  users: () => call<{ users: Account[] }>("/auth/users"),
  createUser: (username: string, password: string, role: string) =>
    send<{ users: Account[] }>("/auth/users", "POST", { username, password, role }),
  updateUser: (username: string, change: { role?: string; active?: boolean; password?: string }) =>
    send<{ users: Account[] }>(`/auth/users/${encodeURIComponent(username)}`, "PATCH", change),
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
  pipeline: () => call<PipelineResponse>("/pipeline"),
  connectors: () => call<ConnectorsResponse>("/pipeline/connectors"),
  uploads: () => call<UploadsResponse>("/intake/uploads"),
  /** a refused file (type, size, empty) comes back as { error } */
  upload: async (file: File): Promise<Upload | { error: string }> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/intake/uploads`, { method: "POST", body: form });
    const out = await res.json().catch(() => ({}));
    if (res.ok) return out as Upload;
    return { error: out.error ?? `upload failed (${res.status})` };
  },
  events: (type?: string, before?: string) => {
    const q = new URLSearchParams({ limit: "20", ...(type ? { type } : {}), ...(before ? { before } : {}) });
    return call<EventLogResponse>(`/pipeline/events?${q}`);
  },
  /** rule errors come back as { errors } so the editor can show them */
  saveRules: async (rules: PipelineRule[]): Promise<PipelineResponse | { errors: Record<string, string> }> => {
    const res = await fetch(`${API_BASE}/pipeline/rules`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rules }) });
    const body = await res.json().catch(() => ({}));
    if (res.ok) return body as PipelineResponse;
    if (res.status === 400 && body.detail) return { errors: body.detail };
    throw new Error(body.error ?? `PUT /pipeline/rules failed: ${res.status}`);
  },
  dryRunRules: async (rules: PipelineRule[]): Promise<DryRunResponse | { errors: Record<string, string> }> => {
    const res = await fetch(`${API_BASE}/pipeline/rules/dry-run`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rules }) });
    const body = await res.json().catch(() => ({}));
    if (res.ok) return body as DryRunResponse;
    if (res.status === 400 && body.detail) return { errors: body.detail };
    throw new Error(`dry run failed: ${res.status}`);
  },
  resetRules: () => call<PipelineResponse>("/pipeline/rules/reset", { method: "POST" }),
  detectNow: (types?: string) => call<{ queued: string | null; note: string | null }>(`/pipeline/detect${types ? `?types=${encodeURIComponent(types)}` : ""}`, { method: "POST" }),
  prompts: () => call<{ prompts: PromptInfo[] }>("/prompts"),
  /** saved as a candidate; prompts used in answering get an evaluation job */
  savePrompt: (name: string, text: string, note: string) =>
    call<{ version: number; evaluationJob: string | null }>(`/prompts/${encodeURIComponent(name)}`, { method: "POST", body: JSON.stringify({ text, note }) }),
  activatePrompt: (name: string, version: number) =>
    call<{ prompts: PromptInfo[] }>(`/prompts/${encodeURIComponent(name)}/activate`, { method: "POST", body: JSON.stringify({ version }) }),
  shadows: () => call<ShadowsResponse>("/shadows"),
  /** build / evaluate / promote are queued as jobs; discard drops the shadow tables at once */
  shadowAction: (name: string, action: "build" | "evaluate" | "promote" | "discard") =>
    call<{ queued?: string | null; note?: string | null; discarded?: string }>(`/shadows/${encodeURIComponent(name)}/${action}`, { method: "POST" }),
  queueJob: (kind: string) =>
    call<{ queued: string | null; note: string | null }>("/jobs", { method: "POST", body: JSON.stringify({ kind, reason: "queued from the Settings page" }) }),
};
