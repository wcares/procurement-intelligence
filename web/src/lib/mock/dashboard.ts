import snapshot from "@/mocks/dashboard.json";

// The home dashboard in mock mode: a snapshot of the real backend's answers (scripts/mock_dashboard.py), so the page
// works without a backend. Drill-downs exist only for the first rows of each ranking; others say so.
type Snapshot = {
  dashboard: unknown;
  rankings: Record<string, unknown>;
  heatmaps: Record<string, unknown>;
  records: Record<string, unknown>;
  recent: unknown;
};
const data = snapshot as unknown as Snapshot;

export const dashboard = () => data.dashboard;

export const recent = () => data.recent;

export function ranking(measure: string, group: string): unknown | null {
  return data.rankings[`${measure}|${group}`] ?? null;
}

export function heatmap(measure: string): unknown | null {
  return data.heatmaps[measure] ?? null;
}

export function records(group: string, key: string, measure: string): unknown | null {
  return data.records[`${group}|${key}|${measure}`] ?? null;
}
