import { assess } from "@/lib/mock/engine";
import type { AssessRequest } from "@/lib/api/types";

const GROUPS = new Set(["GO", "CW", "CS", "NC"]);

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as Partial<AssessRequest> | null;
  if (!body?.countryCode || !body.methodCode || !body.procGroup || !GROUPS.has(body.procGroup)) {
    return Response.json({ error: "countryCode, procGroup (GO|CW|CS|NC) and methodCode are required" }, { status: 400 });
  }
  return Response.json(assess(body as AssessRequest));
}
