"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { RecentChanges } from "@/lib/api/types";

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/** What the pipeline picked up from the sources lately, in planner words; loads on its own so the page never waits. */
export function RecentChangesCard() {
  const [data, setData] = useState<RecentChanges | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    api.recentChanges().then(setData).catch(() => setFailed(true));
  }, []);
  if (failed || !data) return null;
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="mb-3 font-semibold">What changed in the last {data.days} days</h2>
      {data.items.length === 0 ? (
        <p className="text-sm text-ink-muted">No new or changed source records since {day(data.since)}.</p>
      ) : (
        <ul className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {data.items.map((i) => (
            <li key={i.type} className="flex items-baseline gap-2">
              <span className="w-14 shrink-0 text-right font-semibold tabular-nums">{i.count.toLocaleString()}</span>
              <span>
                {i.label}
                <span className="text-xs text-ink-muted"> · latest {day(i.last)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-ink-muted">
        Detected by the data pipeline when it compared each source with what was stored; the tables, passages and
        statistics on this page already include them.
      </p>
    </section>
  );
}
