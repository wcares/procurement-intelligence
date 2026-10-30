"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { AlertsResponse } from "@/lib/api/types";
import { AlertsList } from "./alerts-list";
import { WatchListEditor } from "./watch-list";
import { WatchTrends } from "./watch-trends";
import { PastRecommendations } from "./past-recommendations";
import { OngoingWork } from "@/components/monitoring/ongoing-work";

export function InsightsView() {
  const openProject = useSearchParams().get("project");   // from a package page's project link
  const [data, setData] = useState<AlertsResponse | null>(null);
  const [saved, setSaved] = useState(0);
  const load = useCallback(() => api.alerts().then(setData).catch(() => setData(null)), []);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <div className="grid gap-8 md:grid-cols-[3fr_2fr]">
      <section>
        <div className="mb-3 flex items-baseline gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">Alerts</h2>
          {data && data.unread > 0 && (
            <button className="text-xs underline" onClick={() => api.markAlertsRead().then(setData)}>mark all {data.unread} read</button>
          )}
        </div>
        <p className="mb-3 text-xs text-ink-muted">Changes the pipeline found in what you watch: new and re-issued notices, awards, completion reports.</p>
        {data ? <AlertsList alerts={data.alerts} onRead={(id) => api.markAlertsRead([id]).then(setData)} /> : <p className="text-sm text-ink-muted">Loading…</p>}
      </section>
      <details className="group self-start">
        <summary className="mb-3 flex cursor-pointer list-none items-baseline gap-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">
          Your watch-list
          <span className="text-xs font-normal normal-case group-open:hidden">edit</span>
          <span className="hidden text-xs font-normal normal-case group-open:inline">hide</span>
        </summary>
        <WatchListEditor onSaved={() => (load(), setSaved((n) => n + 1))} />
      </details>
      <section className="md:col-span-2">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-ink-muted">Ongoing work</h2>
        <p className="mb-3 text-xs text-ink-muted">Every package has a status (active, finished, replaced or stale) from what has been published so far; active ones are forecast from where they are now. Open a project for its packages, a package for its live timeline.</p>
        <OngoingWork openProject={openProject} />
      </section>
      <section className="md:col-span-2">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-ink-muted">Trends</h2>
        <p className="mb-3 text-xs text-ink-muted">Median days from tender to award by tender year; hollow points: years whose tenders are not all awarded yet. Recommendations for a package are on the Assess page.</p>
        <WatchTrends version={saved} />
      </section>
      <section className="md:col-span-2">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-ink-muted">Past recommendations</h2>
        <p className="mb-3 text-xs text-ink-muted">The recommendations you asked for on Assess and what you decided; the counts are over everyone&apos;s, so a kind people keep dismissing shows.</p>
        <PastRecommendations />
      </section>
    </div>
  );
}
