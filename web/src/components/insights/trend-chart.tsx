"use client";

import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { AwardTrend } from "@/lib/api/types";
import { cssVar, useECharts } from "@/lib/use-echarts";

/** Median days from tender to award by tender year; years whose tenders are not all awarded yet are hollow. */
export function TrendChart({ trend, height = "h-36" }: { trend: AwardTrend; height?: string }) {
  const option = useMemo<EChartsOption | null>(() => {
    if (!trend.series.length) return null;
    const muted = cssVar("--ink-muted", "#888");
    const line = cssVar("--line", "#ddd");
    const color = cssVar("--series-1", "#2a78d6");
    return {
      grid: { left: 36, right: 8, top: 8, bottom: 22 },
      tooltip: { trigger: "axis", backgroundColor: cssVar("--surface", "#fff"), borderColor: line,
        textStyle: { color: cssVar("--foreground", "#222") },
        formatter: (ps) => {
          const p = (ps as unknown as { dataIndex: number }[])[0];
          const s = trend.series[p.dataIndex];
          return `<b>${s.year}</b>: median ${Math.round(s.median_days)} days (${s.n} packages)${s.incomplete ? "<br/>not all tenders awarded yet" : ""}`;
        } },
      xAxis: { type: "category", data: trend.series.map((s) => String(s.year)), axisLabel: { color: muted, fontSize: 10 },
        axisLine: { lineStyle: { color: line } } },
      yAxis: { type: "value", axisLabel: { color: muted, fontSize: 10 }, splitLine: { lineStyle: { color: line } } },
      series: [{ type: "line", data: trend.series.map((s) => ({ value: s.median_days,
        itemStyle: s.incomplete ? { color: cssVar("--surface", "#fff"), borderColor: color, borderWidth: 2 } : { color } })),
        lineStyle: { width: 2, color }, symbolSize: 8 }],
    } as EChartsOption;
  }, [trend]);
  const ref = useECharts(option);
  if (!option) return <p className="text-xs text-ink-muted">Too few awarded packages for a trend.</p>;
  return <div ref={ref} className={`${height} w-full`} role="img" aria-label="Median days from tender to award by tender year" />;
}
