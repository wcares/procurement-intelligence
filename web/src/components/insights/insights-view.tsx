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
import { SlidersHorizontal } from "lucide-react";

const Panel = ({ title, hint, action, children, className = "" }: { title: string; hint?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) => (
  <section className={`border-t border-line pt-6 ${className}`}>
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        {hint && <p className="mt-1 max-w-prose text-sm text-ink-muted">{hint}</p>}
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
      <div className="mb-8 flex flex-wrap items-end gap-3 pt-8">
        <div>
          <h1 className="text-3xl font-semibold text-brand-strong">Insights</h1>
          <p className="mt-1 text-ink-muted">Changes the pipeline detects in the World Bank data, for what you follow.</p>
        </div>
        <button type="button" onClick={() => setConfigure(true)}
          className="ml-auto inline-flex items-center gap-2 rounded-md border border-line px-3 py-1.5 text-sm transition-colors hover:border-brand-2">
          <SlidersHorizontal size={15} aria-hidden /> Watch-list
          <span className="text-xs text-ink-muted">{following ? `${following} followed` : "nothing followed"}</span>
        </button>
      </div>
      <ConfigureDrawer open={configure} onClose={() => setConfigure(false)} title="Your watch-list" subtitle="Alerts appear when the pipeline records changes inside what you follow.">
        <WatchListEditor onSaved={() => { load(); loadFollowing(); setSaved((n) => n + 1); setConfigure(false); }} />
      </ConfigureDrawer>
      <div className="space-y-6">
        <Panel title="Alerts" hint="New and re-issued notices, awards and completion reports in what you follow."
          action={data && data.unread > 0 ? (
            <button className="rounded-md border border-line px-2.5 py-1 text-xs" onClick={() => api.markAlertsRead().then(setData)}>Mark all {data.unread} read</button>
          ) : undefined}>
          {data ? <AlertsList alerts={data.alerts} onRead={(id) => api.markAlertsRead([id]).then(setData)} /> : <p className="text-sm text-ink-muted">Loading…</p>}
        </Panel>
        <Panel title="Ongoing work" hint="Every package has a status (active, finished, replaced or stale) from what has been published so far; active ones are forecast from where they are now. Open a project for its packages, a package for its live timeline.">
          <OngoingWork openProject={openProject} />
        </Panel>
        <div className="grid gap-x-10 gap-y-6 xl:grid-cols-2">
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
