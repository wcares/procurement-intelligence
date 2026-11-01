"use client";

import { useMemo } from "react";
import type { Options } from "@/lib/api/types";
import { todayLocal } from "@/lib/plan";
import type { PlanState } from "./use-plan";

const field = "w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm outline-none focus:border-brand";

/** The plan's country, project start and deadline (a changed country makes the forecasts stale). */
export function PlanSettings({ s }: { s: PlanState }) {
  const regions = useMemo(() => {
    const by = new Map<string, Options["countries"]>();
    for (const c of s.opts?.countries ?? []) by.set(c.region, [...(by.get(c.region) ?? []), c]);
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [s.opts]);
  return (
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
  );
}
