"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { AssessRequest, AwardTrend } from "@/lib/api/types";
import { Recommendations } from "./recommendations";
import { TrendChart } from "./trend-chart";

/** The award-time trend for the current choice and (on Assess) recommendations for the assessed package. Alerts live on the
 * Insights page only. */
export function InsightsPanel({ procGroup, methodCode, countryCode, assessed, wide = false }: {
  procGroup?: string; methodCode?: string; countryCode?: string; assessed?: AssessRequest | null; wide?: boolean;
}) {
  const [trend, setTrend] = useState<AwardTrend | null>(null);
  useEffect(() => {
    if (!procGroup) return;
    api.trend(procGroup, methodCode, countryCode).then(setTrend).catch(() => setTrend(null));
  }, [procGroup, methodCode, countryCode]);

  const card = "rounded-2xl border border-line bg-surface p-4";
  return (
    <aside className={`text-sm ${wide ? "grid items-start gap-4 xl:grid-cols-2" : "space-y-4"}`}>
      {procGroup && trend && (
        <div className={card}>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">Award time by tender year</h3>
          <p className="text-xs text-ink-muted">
            {trend.scope ? `Median days, ${[trend.scope.method, trend.scope.procGroup].filter(Boolean).join(" ")}${trend.scope.country ? ` in ${trend.scope.label}` : ", all countries"}` : ""}
          </p>
          <TrendChart trend={trend} />
        </div>
      )}
      {assessed !== undefined && (
        <div className={card}>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-muted">Recommendations</h3>
          <Recommendations key={JSON.stringify(assessed)} request={assessed} />
        </div>
      )}
    </aside>
  );
}
