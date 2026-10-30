"use client";

import { useMemo } from "react";
import type { Options } from "@/lib/api/types";
import { todayLocal } from "@/lib/plan";
import { PackageCard } from "./package-card";
import { PlanResults } from "./plan-results";
import { newPackage, type PlanState } from "./use-plan";

const field = "w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm outline-none focus:border-brand";

/** The form: the packages one by one, and the forecast with a button. Edits the same plan as the chat. */
export function ManualPlan({ s }: { s: PlanState }) {
  const regions = useMemo(() => {
    const by = new Map<string, Options["countries"]>();
    for (const c of s.opts?.countries ?? []) by.set(c.region, [...(by.get(c.region) ?? []), c]);
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [s.opts]);

  return (
    <div className="grid gap-6">
      <div className="space-y-4">
        <div className="grid gap-3 rounded-xl border border-line bg-surface p-4 sm:grid-cols-3">
          <label className="text-xs sm:col-span-3">Country
            <select className={field} value={s.countryCode} onChange={(e) => { s.setCountryCode(e.target.value); s.setForecasts({}); }} disabled={!s.opts}>
              {regions.map(([region, cs]) => (
                <optgroup key={region} label={region}>{cs.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</optgroup>
              ))}
            </select>
          </label>
          <label className="text-xs sm:col-span-1">Project start
            <input type="date" className={field} value={s.projectStart} onChange={(e) => s.setProjectStart(e.target.value || todayLocal())} />
          </label>
          <label className="text-xs sm:col-span-2">Deadline for all awards (optional)
            <input type="date" className={field} value={s.deadline ?? ""} onChange={(e) => s.setDeadline(e.target.value || undefined)} />
          </label>
        </div>
        {s.packages.map((p) => (
          <PackageCard key={p.id} pkg={p} others={s.packages.filter((o) => o.id !== p.id)} opts={s.opts} countryCode={s.countryCode}
            forecast={s.forecasts[p.id]} status={s.errors[p.id]} onChange={s.update} onRemove={() => s.remove(p.id)} />
        ))}
        <div className="flex flex-wrap gap-3">
          <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => s.setPackages((ps) => [...ps, newPackage()])}>Add a package</button>
          <button type="button" disabled={!s.opts || s.running || s.packages.length === 0}
            className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50" onClick={() => void s.run()}>
            {s.running ? s.progress || "Forecasting…" : "Forecast the project"}
          </button>
        </div>
        <p className="text-xs text-ink-muted">Your plan is kept in this browser only.</p>
      </div>

      <section className="min-w-0 space-y-4">
        {!s.ran ? (
          <div className="rounded-xl border border-dashed border-line p-10 text-center text-ink-muted">
            Add the packages of the project, then forecast it to see when each is likely to be awarded, which one holds the
            project back, and whether a deadline is realistic.
          </div>
        ) : (
          <>
            <PlanResults packages={s.packages} plan={s.plan} forecasts={s.forecasts} projectStart={s.projectStart} deadline={s.deadline} />
            <p className="text-xs text-ink-muted">
              Each forecast comes from comparable past packages; the project dates combine them in the order you set.
              The system has not learned how packages depend on each other, so treat the project dates as a planning
              aid, not a prediction of the whole project. The Procurement Regulations decide which methods are allowed.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
