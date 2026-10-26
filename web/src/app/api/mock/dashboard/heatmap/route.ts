import { heatmap } from "@/lib/mock/dashboard";

export async function GET(request: Request) {
  const out = heatmap(new URL(request.url).searchParams.get("measure") ?? "delay");
  return out ? Response.json(out) : Response.json({ error: "the heat map shows package measures (award time, long awards)" }, { status: 400 });
}
