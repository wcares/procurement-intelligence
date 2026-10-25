"use client";

import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { HeatmapResponse } from "@/lib/api/types";
import { cssVar, useECharts } from "@/lib/use-echarts";
import { fmt } from "./format";

/** Country x procurement method coloured by the measure; a cell click opens its packages. */
export function Heatmap({ data, onSelect }: { data: HeatmapResponse; onSelect: (country: string, method: string, label: string) => void }) {
  const option = useMemo<EChartsOption>(() => {
    const countries = [...new Set(data.cells.map((c) => c.countryLabel))].sort();
    const methods = [...new Set(data.cells.map((c) => c.method))].sort();
    const values = data.cells.map((c) => c.value);
    const text = cssVar("--muted", "#888");
    return {
      tooltip: { formatter: (p) => { const d = (p as unknown as { data: { name: string; value: number[]; n: number; m: string } }).data; return `${d.name} · ${d.m}<br/>${fmt(data.measure, d.value[2])} (${d.n} awards)`; } },
      grid: { left: 150, right: 16, top: 8, bottom: 100 },
      xAxis: { type: "category", data: methods, axisLabel: { color: text, rotate: 45, fontSize: 11 } },
      yAxis: { type: "category", data: countries, inverse: true, axisLabel: { color: text, fontSize: 11, width: 140, overflow: "truncate" } },
      visualMap: { min: Math.min(...values), max: Math.max(...values), calculable: true, orient: "horizontal", left: "center", bottom: 4, itemHeight: 160, textStyle: { color: text },
        inRange: { color: [cssVar("--risk-low-soft", "#e7f5ec"), cssVar("--risk-medium", "#a15c07"), cssVar("--risk-high", "#b42318")] } },
      series: [{ type: "heatmap", data: data.cells.map((c) => ({ value: [methods.indexOf(c.method), countries.indexOf(c.countryLabel), c.value], name: c.countryLabel, n: c.n, m: c.method, country: c.country })),
        emphasis: { itemStyle: { borderColor: cssVar("--foreground", "#000"), borderWidth: 1 } } }],
    } as EChartsOption;
  }, [data]);
  const ref = useECharts(option, (d) => {
    const cell = d as { country?: string; m?: string; name?: string };
    if (cell.country && cell.m) onSelect(cell.country, cell.m, cell.name ?? cell.country);
  });
  const rows = new Set(data.cells.map((c) => c.country)).size;
  return <div ref={ref} style={{ height: Math.max(300, rows * 18 + 130) }} className="w-full" />;
}
