import type { AssessResponse, ProcGroup } from "@/lib/api/types";

/** One package of a project being planned. Dates are ISO days (YYYY-MM-DD). */
export interface PlanPackage {
  id: string;
  name: string;
  procGroup: ProcGroup;
  methodCode: string;
  sector?: string;
  estimatedValueUsd?: number;
  description?: string;
  /** earliest planned tender notice; the project start when empty */
  tenderStart?: string;
  /** id of a package that must be awarded before this one's tender starts */
  after?: string;
}

/** What the assessment says about one package, reduced to what scheduling needs. */
export interface Forecast {
  p50: number;
  p90: number | null;
  pLong: number | null;
  /** "model" or "historical median": where the typical time comes from */
  basis: string;
  n: number | null;
  scope: string | null;
  highRisks: number;
  /** the flags above low, with their level, e.g. "Re-tendering (high)" */
  risks?: string[];
}

export interface Scheduled {
  id: string;
  start50: string;
  award50: string;
  award90: string;
  /** the slow case was not available, so the typical time stands in for it */
  p90Missing: boolean;
  /** this package waits for another one */
  waitsFor: string | null;
}

export interface ProjectPlan {
  rows: Scheduled[];
  end50: string | null;
  end90: string | null;
  bottleneck: string | null;
  /** package ids that cannot be scheduled (a chain that loops) */
  loops: string[];
}

/** Today as the person's own calendar date (not UTC, which can be a day ahead in the evening). */
export function todayLocal(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + Math.round(days));
  return d.toISOString().slice(0, 10);
}

export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

const later = (a: string, b: string) => (a >= b ? a : b);

export function forecastOf(r: AssessResponse): Forecast | null {
  const p = r.prediction;
  const t = r.timeline;
  const p50 = p?.days_p50 ?? t?.median;
  if (p50 == null) return null;
  return {
    p50,
    p90: p?.days_p90 ?? t?.p90 ?? null,
    pLong: p?.p_long ?? null,
    basis: p?.basis ?? "historical median",
    n: t?.n ?? null,
    scope: t?.scope ?? null,
    highRisks: r.risks.filter((x) => x.level === "high").length,
    risks: r.risks.filter((x) => x.level !== "low").slice(0, 4).map((x) => `${x.label} (${x.level})`),
  };
}

/**
 * Dates for every package that has a forecast. A package with `after` starts when that package is awarded (typical
 * case after its typical time, slow case after its slow time), or at its own tender start if that is later. The
 * project's slow date is the latest slow date of its packages, so it is a cautious figure, not a probability.
 */
export function schedule(packages: PlanPackage[], forecasts: Record<string, Forecast | undefined>, projectStart: string): ProjectPlan {
  const byId = new Map(packages.map((p) => [p.id, p]));
  const done = new Map<string, Scheduled>();
  const loops: string[] = [];

  function resolve(id: string, path: string[]): Scheduled | null {
    const hit = done.get(id);
    if (hit) return hit;
    const pkg = byId.get(id);
    const f = forecasts[id];
    if (!pkg || !f) return null;
    if (path.includes(id)) {
      loops.push(id);
      return null;
    }
    const own = pkg.tenderStart || projectStart;
    let start50 = own;
    let start90 = own;
    let waitsFor: string | null = null;
    if (pkg.after && byId.has(pkg.after)) {
      const prev = resolve(pkg.after, [...path, id]);
      if (prev) {
        start50 = later(own, prev.award50);
        start90 = later(own, prev.award90);
        waitsFor = pkg.after;
      }
    }
    const p90 = f.p90 ?? f.p50;
    const row: Scheduled = {
      id,
      start50,
      award50: addDays(start50, f.p50),
      award90: addDays(start90, Math.max(p90, f.p50)),
      p90Missing: f.p90 == null,
      waitsFor,
    };
    done.set(id, row);
    return row;
  }

  const rows = packages.map((p) => resolve(p.id, [])).filter((r): r is Scheduled => r !== null);
  if (!rows.length) return { rows, end50: null, end90: null, bottleneck: null, loops };
  const last = rows.reduce((a, b) => (b.award50 > a.award50 ? b : a));
  return {
    rows,
    end50: rows.reduce((m, r) => later(m, r.award50), rows[0].award50),
    end90: rows.reduce((m, r) => later(m, r.award90), rows[0].award90),
    bottleneck: last.id,
    loops,
  };
}

/** Against a deadline: packages whose typical date is already past it, and those only the slow case misses. */
export function deadlineCheck(plan: ProjectPlan, deadline: string): { late: string[]; atRisk: string[] } {
  const late = plan.rows.filter((r) => r.award50 > deadline).map((r) => r.id);
  const atRisk = plan.rows.filter((r) => r.award50 <= deadline && r.award90 > deadline).map((r) => r.id);
  return { late, atRisk };
}

/** The forecast as plain text: what the chat model is allowed to quote when asked about the plan (numbers come from here). */
export function resultsText(packages: PlanPackage[], forecasts: Record<string, Forecast | undefined>, plan: ProjectPlan): string {
  const name = (id: string) => packages.find((p) => p.id === id)?.name || "Unnamed package";
  const lines = plan.rows.map((r) => {
    const f = forecasts[r.id];
    if (!f) return `${name(r.id)}: no forecast`;
    const bits = [`typical ${f.p50} days`, f.p90 != null ? `slow case ${f.p90} days` : null,
      f.pLong != null ? `${Math.round(f.pLong * 100)}% chance of over 180 days` : null, `typical award ${r.award50}`,
      f.risks?.length ? `risks: ${f.risks.join(", ")}` : null, r.waitsFor ? `starts after ${name(r.waitsFor)}` : null];
    return `${name(r.id)}: ${bits.filter(Boolean).join(", ")}`;
  });
  if (plan.end50) lines.push(`All awarded by ${plan.end50} (typical) or ${plan.end90} (slow case). Bottleneck: ${plan.bottleneck ? name(plan.bottleneck) : "none"}.`);
  return lines.join("\n");
}
