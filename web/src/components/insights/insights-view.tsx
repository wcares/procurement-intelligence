"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { AlertsResponse } from "@/lib/api/types";
import { AlertsList } from "./alerts-list";
import { WatchListEditor } from "./watch-list";
import { WatchTrends } from "./watch-trends";
import { PastRecommendations } from "./past-recommendations";
import { ConfigureDrawer } from "./configure-drawer";
import { OngoingWork } from "@/components/monitoring/ongoing-work";

const Panel = ({ title, hint, action, children, className = "" }: { title: string; hint?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) => (
  <section className={`rounded-2xl border border-line bg-surface p-5 ${className}`}>
    <div className="mb-3 flex items-start justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {hint && <p className="mt-0.5 max-w-prose text-xs text-ink-muted">{hint}</p>}
      </div>
      {action}
    </div>
    {children}
  </section>
);

export function InsightsView() {
  const openProject = useSearchParams().get("project");   // from a package page's project link
  const [data, setData] = useState<AlertsResponse | null>(null);
  const [saved, setSaved] = useState(0);
  const [configure, setConfigure] = useState(false);
  const [following, setFollowing] = useState(0);   // how many things the watch-list picks
  const load = useCallback(() => api.alerts().then(setData).catch(() => setData(null)), []);
  const loadFollowing = useCallback(() => api.watch().then((r) => setFollowing(Object.values(r.watch).reduce((n, v) => n + v.length, 0))).catch(() => null), []);
  useEffect(() => {
    load();
    loadFollowing();
  }, [load, loadFollowing]);
  return (
    // the bar sits flush under the header: the negative margins cancel the page padding
    <div className="-mt-8">
      <div className="-mx-4 mb-6 flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 lg:-mx-8 lg:px-8">
        <h1 className="text-[15px] font-semibold tracking-tight">Insights</h1>
        <p className="hidden text-xs text-ink-muted md:block">Changes the pipeline detects in the World Bank data, for what you follow.</p>
        <button type="button" onClick={() => setConfigure(true)}
          className="ml-auto inline-flex items-center gap-2 rounded-lg border border-line bg-subtle px-3 py-1.5 text-sm font-medium transition hover:border-brand">
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <circle cx="8" cy="8" r="2.2" />
            <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1" />
          </svg>
          Configure
          <span className={`rounded-full px-1.5 text-xs ${following ? "bg-brand-soft text-brand" : "bg-background text-ink-muted"}`}>{following ? `${following} followed` : "nothing followed"}</span>
        </button>
      </div>
      <ConfigureDrawer open={configure} onClose={() => setConfigure(false)} title="Your watch-list" subtitle="Alerts appear when the pipeline records changes inside what you follow.">
        <WatchListEditor onSaved={() => { load(); loadFollowing(); setSaved((n) => n + 1); setConfigure(false); }} />
      </ConfigureDrawer>
      <div className="space-y-6">
        <Panel title="Alerts" hint="New and re-issued notices, awards and completion reports in what you follow."
          action={data && data.unread > 0 ? (
            <button className="rounded-lg bg-brand-soft px-2.5 py-1 text-xs font-medium text-brand" onClick={() => api.markAlertsRead().then(setData)}>Mark all {data.unread} read</button>
          ) : undefined}>
          {data ? <AlertsList alerts={data.alerts} onRead={(id) => api.markAlertsRead([id]).then(setData)} /> : <p className="text-sm text-ink-muted">Loading…</p>}
        </Panel>
        <Panel title="Ongoing work" hint="Every package has a status (active, finished, replaced or stale) from what has been published so far; active ones are forecast from where they are now. Open a project for its packages, a package for its live timeline.">
          <OngoingWork openProject={openProject} />
        </Panel>
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="Trends" hint="Median days from tender to award by tender year; hollow points: years whose tenders are not all awarded yet. Recommendations for a package are on the Assess page.">
            <WatchTrends version={saved} />
          </Panel>
          <Panel title="Past recommendations" hint="The recommendations you asked for on Assess and what you decided; the counts are over everyone's, so a kind people keep dismissing shows.">
            <PastRecommendations />
          </Panel>
        </div>
      </div>
    </div>
  );
}
