import { ranking } from "@/lib/mock/dashboard";

export async function GET(request: Request) {
  const q = new URL(request.url).searchParams;
  const out = ranking(q.get("measure") ?? "delay", q.get("group") ?? "country");
  return out ? Response.json(out) : Response.json({ error: "this measure is not counted for that grouping" }, { status: 400 });
}
