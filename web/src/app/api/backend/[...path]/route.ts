import type { NextRequest } from "next/server";

// The browser calls /api/backend/<path>; this forwards to the backend named by API_URL, read on every request so one
// built image works against any backend (local, Compose, cloud). Without API_URL it serves the in-app mock.
const HOP_HEADERS = new Set(["connection", "content-length", "host", "keep-alive", "transfer-encoding"]);

async function forward(req: NextRequest, ctx: RouteContext<"/api/backend/[...path]">): Promise<Response> {
  const { path } = await ctx.params;
  const { search } = new URL(req.url);
  const base = process.env.API_URL?.replace(/\/$/, "");
  const target = base ? `${base}/${path.join("/")}${search}` : new URL(`/api/mock/${path.join("/")}${search}`, req.url);
  const headers = new Headers();
  req.headers.forEach((v, k) => !HOP_HEADERS.has(k) && headers.set(k, v));
  const body = req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer();
  try {
    const res = await fetch(target, { method: req.method, headers, body, redirect: "manual", cache: "no-store" });
    const out = new Headers();
    res.headers.forEach((v, k) => !HOP_HEADERS.has(k) && k !== "content-encoding" && out.set(k, v));
    return new Response(res.body, { status: res.status, headers: out });
  } catch (e) {
    return Response.json({ detail: `backend not reachable: ${(e as Error).message}` }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const DELETE = forward;
