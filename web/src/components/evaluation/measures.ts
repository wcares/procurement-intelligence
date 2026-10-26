import type { EvalRun } from "@/lib/api/types";

/** The measures on a 0-1 scale, in fixed series order (colour follows the measure, --series-N). */
export const MEASURES: { key: string; label: string; value: (r: EvalRun) => number | null }[] = [
  { key: "p5", label: "Search precision (top 5)", value: (r) => r.hybrid_p5 ?? null },
  { key: "r10", label: "Search recall (top 10)", value: (r) => r.hybrid_r10 ?? null },
  { key: "gate", label: "Evidence-check precision", value: (r) => r.gate_prec ?? null },
  { key: "answered", label: "Answerable questions answered", value: (r) => ratio(r.answered, r.answerable) },
  { key: "traps", label: "Trap questions refused", value: (r) => ratio(r.refused_traps, r.traps) },
  { key: "supported", label: "Sentences supported", value: (r) => ratio(r.supported_sentences, r.sentences) },
];

export function ratio(a?: number, b?: number): number | null {
  return a != null && b ? a / b : null;
}

export const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

/** A run's time ("2026-10-25 02:04 UTC") as ISO, and as local date and time for display. */
export const isoOf = (t: string) => t.replace(" UTC", "Z").replace(" ", "T");
export const localTime = (t: string) => new Date(isoOf(t)).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
