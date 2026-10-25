import type { FeedbackRequest } from "@/lib/api/types";

const RATINGS = new Set(["useful", "not_useful", "bad_citation"]);

// The mock keeps nothing; it only validates like the backend so the UI behaves the same offline.
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Partial<FeedbackRequest> | null;
  if (!body?.responseId || !body.rating || !RATINGS.has(body.rating) || (body.rating === "bad_citation" && !body.citationId)) {
    return Response.json({ error: "responseId and rating (useful|not_useful|bad_citation, with citationId) are required" }, { status: 400 });
  }
  return Response.json({ ok: true, feedbackId: crypto.randomUUID() });
}
