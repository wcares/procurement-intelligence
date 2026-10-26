"use client";

import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { SimilarPackage } from "@/lib/api/types";
import { cssVar, useECharts } from "@/lib/use-echarts";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

/** Similar contracts by value (log scale) and tender-to-award time, re-tendered ones in a warning colour; click a point to
 * jump to its row. Contracts missing either number are only in the list. */
function SimilarScatter({ items, onSelect }: { items: SimilarPackage[]; onSelect: (id: string) => void }) {
  const plotted = useMemo(() => items.filter((p) => p.valueUsd != null && p.valueUsd > 0 && p.tenderToAwardDays != null), [items]);
  const option = useMemo<EChartsOption | null>(() => {
    if (plotted.length < 2) return null;
    const muted = cssVar("--ink-muted", "#888");
    const point = (p: SimilarPackage) => ({ value: [p.valueUsd, p.tenderToAwardDays], id: p.packageId, name: p.description,
      where: `${p.projectId} · ${p.countryCode} · ${p.method}` });
    const series = (name: string, rebid: boolean, color: string) => ({ type: "scatter" as const, name, symbolSize: 12,
      itemStyle: { color }, data: plotted.filter((p) => p.rebid === rebid).map(point) });
    return {
      grid: { left: 56, right: 24, top: 30, bottom: 44 },
      legend: { top: 0, right: 0, textStyle: { color: muted } },
      tooltip: { trigger: "item", formatter: (p) => {
        const d = (p as unknown as { data: { value: [number, number]; name: string; where: string } }).data;
        return `<b>${d.name.slice(0, 80)}</b><br/>${d.where}<br/>${usd.format(d.value[0])} · ${d.value[1]} days`;
      } },
      xAxis: { type: "log", name: "contract value (USD)", nameLocation: "middle", nameGap: 28, axisLabel: { color: muted, formatter: (v: number) => usd.format(v) },
        splitLine: { lineStyle: { color: cssVar("--line", "#ddd") } } },
      yAxis: { type: "value", name: "days to award", axisLabel: { color: muted }, splitLine: { lineStyle: { color: cssVar("--line", "#ddd") } } },
      series: [series("awarded first time", false, cssVar("--brand", "#1f5fbf")), series("re-tendered", true, cssVar("--risk-medium", "#a15c07"))],
    } as EChartsOption;
  }, [plotted]);
  const ref = useECharts(option, (d) => {
    const id = (d as { id?: string }).id;
    if (id) onSelect(id);
  });
  return option ? <div ref={ref} className="mb-3 h-64 w-full rounded-xl border border-line bg-surface" /> : null;
}

export function SimilarPackages({ items }: { items: SimilarPackage[] }) {
  const show = (id: string) => {
    const el = document.getElementById(`similar-${id}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.classList.add("ring-2", "ring-brand");
    setTimeout(() => el?.classList.remove("ring-2", "ring-brand"), 1500);
  };
  return (
    <div>
      <h3 className="mb-1 font-semibold">Similar past contracts</h3>
      <p className="mb-3 text-xs text-ink-muted">Awarded packages whose description is closest to yours, and how long they took from tender to award. Click a point for its row.</p>
      <SimilarScatter items={items} onSelect={show} />
      <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
        {items.map((p) => (
          <li key={p.packageId} id={`similar-${p.packageId}`} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3 text-sm">
            <span className="min-w-0 flex-1 basis-64">{p.description}</span>
            <span className="text-xs text-ink-muted">
              {p.projectId} · {p.countryCode} · {p.method}
            </span>
            <span className="tabular-nums">{p.tenderToAwardDays != null ? `${p.tenderToAwardDays} days` : "time not known"}</span>
            {p.valueUsd != null && <span className="tabular-nums text-ink-muted">{usd.format(p.valueUsd)}</span>}
            {p.rebid && <span className="rounded bg-risk-medium-soft px-1.5 py-0.5 text-xs text-risk-medium">re-tendered</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
