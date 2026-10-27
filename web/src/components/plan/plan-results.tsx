"use client";

import type { PlanPackage, ProjectPlan, Forecast } from "@/lib/plan";
import { daysBetween, deadlineCheck } from "@/lib/plan";

const fmt = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const date = (iso: string) => fmt.format(new Date(`${iso}T00:00:00Z`));

/** Project summary, deadline check and a bar per package: solid to the typical award date, pale to the slow case. */
export function PlanResults({ packages, plan, forecasts, projectStart, deadline }: {
  packages: PlanPackage[];
  plan: ProjectPlan;
  forecasts: Record<string, Forecast | undefined>;
  projectStart: string;
  deadline?: string;
}) {
  const name = (id: string) => packages.find((p) => p.id === id)?.name || "Unnamed package";
  const start = plan.rows.reduce((m, r) => (r.start50 < m ? r.start50 : m), projectStart);
  const end = deadline && deadline > (plan.end90 ?? "") ? deadline : plan.end90 ?? projectStart;
  const span = Math.max(1, daysBetween(start, end));
  const pct = (iso: string) => `${Math.max(0, Math.min(100, (daysBetween(start, iso) / span) * 100))}%`;
  const check = deadline ? deadlineCheck(plan, deadline) : null;
  const missing = packages.filter((p) => !forecasts[p.id]);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Tile label="Typical: all awarded by" value={plan.end50 ? date(plan.end50) : "–"} />
        <Tile label="Slow case: all awarded by" value={plan.end90 ? date(plan.end90) : "–"} note="latest slow date of any package" />
        <Tile label="Likely bottleneck" value={plan.bottleneck ? name(plan.bottleneck) : "–"} note="the package awarded last" />
      </div>

      {check && deadline && (
        <div className={`rounded-lg px-4 py-3 text-sm ${check.late.length ? "bg-risk-high-soft text-risk-high" : check.atRisk.length ? "bg-risk-medium-soft text-risk-medium" : "bg-subtle text-ink-muted"}`}>
          {check.late.length === 0 && check.atRisk.length === 0
            ? `Every package is awarded by ${date(deadline)} even in the slow case.`
            : <>
                {check.late.length > 0 && <p>Typical date is after {date(deadline)}: {check.late.map(name).join(", ")}.</p>}
                {check.atRisk.length > 0 && <p>Only the slow case misses {date(deadline)}: {check.atRisk.map(name).join(", ")}.</p>}
              </>}
        </div>
      )}

      <div className="rounded-xl border border-line bg-surface p-4">
        <p className="mb-3 text-xs text-ink-muted">
          {date(start)} to {date(end)}. Solid bar: tender notice to typical award. Pale: to the slow case (1 in 10).
        </p>
        <div className="space-y-3">
          {plan.rows.map((r) => {
            const f = forecasts[r.id];
            return (
              <div key={r.id}>
                <div className="flex flex-wrap justify-between gap-x-3 text-xs">
                  <span className="font-medium">{name(r.id)}{r.waitsFor && <span className="font-normal text-ink-muted"> · after {name(r.waitsFor)}</span>}</span>
                  <span className="tabular-nums text-ink-muted">
                    {date(r.award50)} ({f?.p50} days){r.p90Missing ? "" : ` · slow ${date(r.award90)}`}
                  </span>
                </div>
                <div className="relative mt-1 h-3 rounded bg-subtle">
                  <div className="absolute inset-y-0 rounded bg-brand/30" style={{ left: pct(r.start50), width: `calc(${pct(r.award90)} - ${pct(r.start50)})` }} />
                  <div className="absolute inset-y-0 rounded bg-brand" style={{ left: pct(r.start50), width: `calc(${pct(r.award50)} - ${pct(r.start50)})` }} />
                  {deadline && deadline >= start && deadline <= end && <div className="absolute inset-y-[-3px] w-0.5 bg-risk-high" style={{ left: pct(deadline) }} />}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {plan.loops.length > 0 && <p className="text-xs text-risk-high">These packages wait for each other in a loop: {plan.loops.map(name).join(", ")}. Break the loop to get dates.</p>}
      {missing.length > 0 && (
        <p className="text-xs text-ink-muted">
          No forecast for {missing.map((p) => p.name || "an unnamed package").join(", ")}: too few comparable packages, or the forecast was not run.
        </p>
      )}
    </div>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
      {note && <p className="text-xs text-ink-muted">{note}</p>}
    </div>
  );
}
