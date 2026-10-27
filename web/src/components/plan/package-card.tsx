"use client";

import { useState } from "react";
import type { AssessRequest, Options, ProcGroup } from "@/lib/api/types";
import type { Forecast, PlanPackage } from "@/lib/plan";
import { GoalPanel } from "@/components/assess/goal-panel";

const field = "w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm outline-none focus:border-brand";

/** One package of the project: its details, what the forecast says, and the goal search for it. */
export function PackageCard({ pkg, others, opts, countryCode, forecast, status, onChange, onRemove }: {
  pkg: PlanPackage;
  others: PlanPackage[];
  opts: Options | null;
  countryCode: string;
  forecast?: Forecast;
  status?: string;
  onChange: (p: PlanPackage) => void;
  onRemove: () => void;
}) {
  const [goal, setGoal] = useState(false);
  const methods = opts?.methods.filter((m) => m.procGroups.includes(pkg.procGroup)) ?? [];
  function setGroup(g: ProcGroup) {
    const keep = opts?.methods.some((m) => m.code === pkg.methodCode && m.procGroups.includes(g));
    onChange({ ...pkg, procGroup: g, methodCode: keep ? pkg.methodCode : (opts?.methods.find((m) => m.procGroups.includes(g))?.code ?? "") });
  }
  const request: AssessRequest = {
    countryCode, procGroup: pkg.procGroup, methodCode: pkg.methodCode, sector: pkg.sector,
    estimatedValueUsd: pkg.estimatedValueUsd, description: pkg.description,
  };
  return (
    <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
      <div className="flex items-center gap-2">
        <input className={`${field} font-medium`} placeholder="Package name, e.g. Rural roads, lot 1" value={pkg.name} onChange={(e) => onChange({ ...pkg, name: e.target.value })} />
        <button type="button" className="shrink-0 text-xs text-ink-muted underline" onClick={onRemove}>Remove</button>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-xs">What is bought
          <select className={field} value={pkg.procGroup} onChange={(e) => setGroup(e.target.value as ProcGroup)} disabled={!opts}>
            {opts?.procGroups.map((g) => <option key={g.code} value={g.code}>{g.label}</option>)}
          </select>
        </label>
        <label className="text-xs">Method
          <select className={field} value={pkg.methodCode} onChange={(e) => onChange({ ...pkg, methodCode: e.target.value })} disabled={!opts}>
            {methods.map((m) => <option key={m.code} value={m.code}>{m.label} ({m.code})</option>)}
          </select>
        </label>
        <label className="text-xs">Sector (optional)
          <select className={field} value={pkg.sector ?? ""} onChange={(e) => onChange({ ...pkg, sector: e.target.value || undefined })} disabled={!opts}>
            <option value="">Any</option>
            {opts?.sectors.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label className="text-xs">Estimated value, US$ (optional)
          <input type="number" min={0} className={field} value={pkg.estimatedValueUsd ?? ""} onChange={(e) => onChange({ ...pkg, estimatedValueUsd: e.target.value ? Number(e.target.value) : undefined })} />
        </label>
        <label className="text-xs">Tender notice (blank: project start)
          <input type="date" className={field} value={pkg.tenderStart ?? ""} onChange={(e) => onChange({ ...pkg, tenderStart: e.target.value || undefined })} />
        </label>
        <label className="text-xs">Starts after the award of
          <select className={field} value={pkg.after ?? ""} onChange={(e) => onChange({ ...pkg, after: e.target.value || undefined })}>
            <option value="">Nothing (independent)</option>
            {others.map((o) => <option key={o.id} value={o.id}>{o.name || "Unnamed package"}</option>)}
          </select>
        </label>
      </div>
      <label className="block text-xs">Short description (optional; finds similar past contracts)
        <input className={field} value={pkg.description ?? ""} maxLength={2000} onChange={(e) => onChange({ ...pkg, description: e.target.value })} />
      </label>
      {status && <p className="text-xs text-risk-high">{status}</p>}
      {forecast && (
        <p className="text-xs text-ink-muted">
          Typical {forecast.p50} days{forecast.p90 != null ? `, slow case ${forecast.p90}` : ""}
          {forecast.pLong != null ? `, ${Math.round(forecast.pLong * 100)}% chance of over 180 days` : ""}
          {forecast.n != null ? ` · from ${forecast.n} comparable packages (${forecast.scope})` : ""}
          {forecast.highRisks ? ` · ${forecast.highRisks} high risk flag${forecast.highRisks > 1 ? "s" : ""}` : ""}
          {" · "}<button type="button" className="underline" onClick={() => setGoal(!goal)}>{goal ? "Hide goal" : "Set a goal for this package"}</button>
        </p>
      )}
      {goal && <GoalPanel request={request} />}
    </div>
  );
}
