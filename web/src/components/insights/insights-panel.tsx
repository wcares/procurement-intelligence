"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { AlertsResponse, AssessRequest, AwardTrend } from "@/lib/api/types";
import { AlertsList } from "./alerts-list";
import { Recommendations } from "./recommendations";
import { TrendChart } from "./trend-chart";

/** The compact side panel next to Ask and Assess: unread alerts, the award-time trend for the current choice and (on
 * Assess) recommendations for the assessed package; the Insights page has the details. */
export function InsightsPanel({ procGroup, methodCode, countryCode, assessed }: {
  procGroup?: string; methodCode?: string; countryCode?: string; assessed?: AssessRequest | null;
}) {
  const [alerts, setAlerts] = useState<AlertsResponse | null>(null);
  const [trend, setTrend] = useState<AwardTrend | null>(null);
  useEffect(() => {
    api.alerts().then(setAlerts).catch(() => setAlerts(null));
  }, []);
  useEffect(() => {
    if (!procGroup) return;
    api.trend(procGroup, methodCode, countryCode).then(setTrend).catch(() => setTrend(null));
  }, [procGroup, methodCode, countryCode]);

  const unread = alerts?.alerts.filter((a) => !a.read).slice(0, 3) ?? [];
  return (
    <aside className="space-y-4 rounded-xl border border-line bg-surface p-4 text-sm">
      <div>
        <div className="mb-1 flex items-baseline justify-between">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Alerts</h3>
          <Link href="/insights" className="text-xs underline">all{alerts ? ` (${alerts.unread} new)` : ""}</Link>
        </div>
        {alerts && alerts.alerts.length === 0 ? (
          <p className="text-xs text-muted">None. <Link href="/insights" className="underline">Set a watch-list</Link> to get alerts on what you follow.</p>
        ) : unread.length ? <AlertsList alerts={unread} compact /> : <p className="text-xs text-muted">No new alerts.</p>}
      </div>
      {procGroup && trend && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Award time by tender year</h3>
          <p className="text-xs text-muted">
            {trend.scope ? `Median days, ${[trend.scope.method, trend.scope.procGroup].filter(Boolean).join(" ")}${trend.scope.country ? ` in ${trend.scope.label}` : ", all countries"}` : ""}
          </p>
          <TrendChart trend={trend} />
        </div>
      )}
      {assessed !== undefined && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Recommendations</h3>
          <Recommendations key={JSON.stringify(assessed)} request={assessed} />
        </div>
      )}
    </aside>
  );
}
