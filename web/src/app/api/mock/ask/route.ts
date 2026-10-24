import { ask } from "@/lib/mock/engine";
import type { AskRequest } from "@/lib/api/types";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Partial<AskRequest> | null;
  const question = body?.question?.trim();
  if (!question) {
    return Response.json({ error: "question is required" }, { status: 400 });
  }
  return Response.json(ask({ ...body, question }));
}
