import type { AskRequest, AskResponse, AssessRequest, AssessResponse, FeedbackRequest, FeedbackResponse, Options } from "./types";

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
};
