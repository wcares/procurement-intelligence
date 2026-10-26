import type { DashMeasure } from "@/lib/api/types";

export const fmt = (m: Pick<DashMeasure, "unit">, v: number | null | undefined): string =>
  v == null ? "–" : m.unit === "share" ? `${Math.round(v * 100)}%` : m.unit === "days" ? `${Math.round(v)} days` : m.unit === "score" ? v.toFixed(2) : v.toFixed(1);
