import type { ConfigSetting, ConfigUpdate } from "@/lib/api/types";

// Mock mode has no backend to tune: the page shows the settings and their defaults, and refuses changes.
const SETTINGS: ConfigSetting[] = [
  { key: "search_k", label: "Passages retrieved per question", group: "Retrieval", type: "int", value: 12, default: 12, editable: false, note: "Mock mode: start the Python backend to change settings.", min: 1, max: 50 },
  { key: "decide_min", label: "Decision threshold", group: "Evidence", type: "float", value: 0.5, default: 0.5, editable: false, note: "Mock mode: start the Python backend to change settings.", min: 0.05, max: 0.99 },
];

export async function GET() {
  return Response.json({ settings: SETTINGS });
}

export async function PUT(request: Request) {
  const body = (await request.json().catch(() => null)) as ConfigUpdate | null;
  const detail = Object.fromEntries(Object.keys(body?.values ?? {}).map((k) => [k, "mock mode: settings are read-only"]));
  return Response.json({ error: "invalid settings", detail }, { status: 400 });
}
