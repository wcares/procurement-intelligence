"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { PackageDetail } from "@/lib/api/types";
import { ForecastSummary } from "./forecast-summary";
import { LiveTimeline } from "./live-timeline";
import { StatusBadge } from "./status-badge";

/** One package: its status and why, the live timeline and forecast (active ones), and every notice published for it. */
export function PackageView() {
  const id = useSearchParams().get("id") ?? "";
  const [p, setP] = useState<PackageDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (id) api.monitoredPackage(id).then(setP).catch((e) => setError((e as Error).message));
  }, [id]);
  if (!id) return <p className="text-sm text-ink-muted">No package chosen.</p>;
  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!p) return <p className="text-sm text-ink-muted">Loading…</p>;
  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs text-ink-muted"><Link href={`/insights?project=${encodeURIComponent(p.projectId)}`} className="underline">{p.projectName}</Link> · {p.projectId}</p>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">{p.description}</h1>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <StatusBadge status={p.status} phase={p.phase} />
          <span className="text-ink-muted">{p.procGroup}{p.methodCode ? ` · ${p.methodCode}` : ""} · {p.packageId}</span>
        </p>
        <p className="mt-1 text-xs text-ink-muted">Why: {p.reason}.{p.closingDate ? ` Project closes ${p.closingDate}.` : ""}</p>
      </div>
      {p.forecast ? (
        <section className="space-y-3 rounded-xl border border-line bg-surface p-4">
          <h2 className="text-sm font-semibold">From where it is now ({p.forecast.asOf})</h2>
          <LiveTimeline f={p.forecast} closingDate={p.closingDate} />
          <ForecastSummary f={p.forecast} />
        </section>
      ) : (
        <p className="text-sm text-ink-muted">{p.status === "stale" ? "No forecast for a stale package: its outcome is unknown." : "Not active: nothing to forecast."}</p>
      )}
      {p.isr && (
        <section className="text-sm">
          <h2 className="mb-1 font-semibold">Project&apos;s newest ISR ({p.isr.date})</h2>
          <ul className="text-xs">
            {Object.entries(p.isr.ratings).map(([k, [prev, cur]]) => <li key={k}>{k.toUpperCase()}: {prev} → {cur}</li>)}
          </ul>
        </section>
      )}
      <section>
        <h2 className="mb-2 text-sm font-semibold">Notices published ({p.notices.length})</h2>
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface text-xs">
          {p.notices.map((n) => (
            <li key={n.noticeId} className="flex flex-wrap gap-x-3 px-3 py-2">
              <span className="w-24 tabular-nums">{n.date}</span>
              <span className="flex-1">{n.type}{n.version ? ` (version ${n.version})` : ""}</span>
              {n.awardDate && <span className="text-ink-muted">award {n.awardDate}</span>}
              <a className="underline" target="_blank" rel="noreferrer" href={`https://projects.worldbank.org/en/projects-operations/procurement-detail/${n.noticeId}`}>notice</a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
