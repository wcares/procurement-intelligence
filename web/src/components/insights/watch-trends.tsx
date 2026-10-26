"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { AwardTrend, WatchList } from "@/lib/api/types";
import { TrendChart } from "./trend-chart";

const GROUPS: Record<string, string> = { GO: "Goods", CW: "Civil Works", CS: "Consulting Services", NC: "Non-Consulting Services" };

/** Award time by tender year for each procurement group (and method) the planner watches, at most four charts; a
 * single watched country narrows them when it has enough packages. */
export function WatchTrends({ version }: { version: number }) {
  const [trends, setTrends] = useState<{ key: string; label: string; trend: AwardTrend }[] | null>(null);
  useEffect(() => {
    api.watch().then(async ({ watch }: { watch: WatchList }) => {
      const groups = watch.proc_group.length ? watch.proc_group : [];
      const methods = watch.method.length ? watch.method : [undefined];
      const country = watch.country.length === 1 ? watch.country[0] : undefined;
      const pairs = groups.flatMap((g) => methods.map((m) => [g, m] as const)).slice(0, 4);
      const out = await Promise.all(pairs.map(async ([g, m]) => ({ key: `${g}/${m ?? ""}`, label: `${GROUPS[g] ?? g}${m ? `, ${m}` : ""}`,
        trend: await api.trend(g, m, country) })));
      setTrends(out.filter((t) => t.trend.series.length));
    }).catch(() => setTrends([]));
  }, [version]);
  if (trends === null) return <p className="text-xs text-muted">Loading…</p>;
  if (!trends.length) return <p className="text-xs text-muted">Add a procurement group to your watch-list to see its award-time trend.</p>;
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {trends.map((t) => (
        <div key={t.key} className="rounded-lg border border-line bg-surface p-3">
          <p className="text-xs font-medium">{t.label}{t.trend.scope?.country ? ` · ${t.trend.scope.label}` : " · all countries"}</p>
          <TrendChart trend={t.trend} />
        </div>
      ))}
    </div>
  );
}
