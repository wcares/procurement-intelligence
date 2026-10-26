"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { LiveForecast } from "@/lib/api/types";
import { ForecastSummary } from "./forecast-summary";
import { LiveTimeline } from "./live-timeline";

export interface Started {
  tenderStart?: string;
  awardDate?: string;
  reissued?: boolean;
  closingDate?: string;
}

/** The "already started?" fields on the Assess form: what the planner knows now about a package under way. */
export function StartedFields({ value, onChange }: { value: Started; onChange: (v: Started) => void }) {
  const field = "w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm";
  return (
    <details className="text-sm" open={!!value.tenderStart}>
      <summary className="cursor-pointer text-xs font-medium text-ink-muted">Already started? Forecast from where it is now</summary>
      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
        <label>Tender published<input type="date" className={field} value={value.tenderStart ?? ""}
          onChange={(e) => onChange({ ...value, tenderStart: e.target.value || undefined })} /></label>
        <label>Awarded on (if)<input type="date" className={field} value={value.awardDate ?? ""}
          onChange={(e) => onChange({ ...value, awardDate: e.target.value || undefined })} /></label>
        <label>Project closes<input type="date" className={field} value={value.closingDate ?? ""}
          onChange={(e) => onChange({ ...value, closingDate: e.target.value || undefined })} /></label>
        <label className="flex items-center gap-1 pt-4"><input type="checkbox" checked={!!value.reissued}
          onChange={(e) => onChange({ ...value, reissued: e.target.checked })} /> a notice was re-issued</label>
      </div>
    </details>
  );
}

/** The forecast for the package as the planner describes it (POST /monitoring/forecast). */
export function StartedForecast({ procGroup, methodCode, started }: { procGroup: string; methodCode: string; started: Started }) {
  const [f, setF] = useState<LiveForecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.describeForecast({ procGroup, methodCode, ...started }).then(setF).catch((e) => setError((e as Error).message));
  }, [procGroup, methodCode, started]);
  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!f) return <p className="text-sm text-ink-muted">Forecasting from where it is…</p>;
  return (
    <div className="space-y-3 rounded-xl border border-brand bg-surface p-4">
      <h3 className="text-sm font-semibold">From where it is now ({f.asOf})</h3>
      <LiveTimeline f={f} closingDate={started.closingDate} />
      <ForecastSummary f={f} />
    </div>
  );
}
