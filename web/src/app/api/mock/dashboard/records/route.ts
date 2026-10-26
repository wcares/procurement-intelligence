import { records } from "@/lib/mock/dashboard";

export async function GET(request: Request) {
  const q = new URL(request.url).searchParams;
  const out = records(q.get("group") ?? "", q.get("key") ?? "", q.get("measure") ?? "delay");
  return out ? Response.json(out) : Response.json({ error: "the demo data includes records only for the first rows of each ranking" }, { status: 400 });
}
