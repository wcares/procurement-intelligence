"use client";

import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { EvalRun } from "@/lib/api/types";
import { cssVar, useECharts } from "@/lib/use-echarts";
import { isoOf, localTime, MEASURES, pct } from "./measures";

/** The measures per evaluation run over time (one 0-100% axis); dashed lines mark the changes made between runs
 * (refresh, retrain, promotion, prompt activation). The table below the chart is the same data as text. */
export function QualityChart({ runs }: { runs: EvalRun[] }) {
  const option = useMemo<EChartsOption | null>(() => {
    if (runs.length < 2) return null;
    const muted = cssVar("--muted", "#888");
    const line = cssVar("--line", "#ddd");
    const changes = runs.flatMap((r) => r.changesBefore ?? []);
    return {
      grid: { left: 48, right: 16, top: 64, bottom: 32 },
      legend: { top: 0, left: 0, textStyle: { color: muted }, itemWidth: 14, itemHeight: 8 },
      tooltip: {
        trigger: "axis",
        backgroundColor: cssVar("--surface", "#fff"), borderColor: line,
        textStyle: { color: cssVar("--foreground", "#222") },
        formatter: (ps) => {
          const items = ps as unknown as { axisValue: number; marker: string; seriesName: string; value: [string, number | null] }[];
          const run = runs.find((r) => new Date(isoOf(r.time)).getTime() === items[0].axisValue);
          const rows = items.filter((p) => p.value[1] != null).map((p) => `${p.marker}${p.seriesName}: <b>${pct(p.value[1])}</b>`);
          const before = (run?.changesBefore ?? []).map((c) => `· ${c.what}: ${c.detail}`);
          return [`<b>${run ? localTime(run.time) : ""}</b>`, ...rows, ...(before.length ? ["<br/>Changes since the run before:", ...before] : [])].join("<br/>");
        },
      },
      xAxis: { type: "time", axisLabel: { color: muted }, axisLine: { lineStyle: { color: line } } },
      yAxis: { type: "value", min: 0, max: 1, axisLabel: { color: muted, formatter: (v: number) => `${v * 100}%` },
        splitLine: { lineStyle: { color: line } } },
      series: MEASURES.map((m, i) => ({
        type: "line" as const, name: m.label, connectNulls: true, symbolSize: 8, lineStyle: { width: 2 },
        itemStyle: { color: cssVar(`--series-${i + 1}`, "#888") },
        data: runs.map((r) => [isoOf(r.time), m.value(r)]),
        ...(i === 0 && changes.length ? {
          markLine: { symbol: "none", silent: true, label: { show: false },
            lineStyle: { color: muted, type: "dashed" as const, width: 1 },
            data: changes.map((c) => ({ xAxis: c.at })) },
        } : {}),
      })),
    } as EChartsOption;
  }, [runs]);
  const ref = useECharts(option);
  if (!option) return <p className="text-sm text-muted">At least two evaluation runs are needed for a trend.</p>;
  return <div ref={ref} className="h-80 w-full" role="img" aria-label="Evaluation measures per run over time" />;
}
