"use client";

import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { LiveForecast } from "@/lib/api/types";
import { cssVar, useECharts } from "@/lib/use-echarts";

const DAY = 86400000;
const t = (d: string) => new Date(d + "T00:00:00Z").getTime();

/** A package on a calendar: what has happened (solid), what is forecast (faded, with the slow case as a lighter tail),
 * a line for today and, when known, one for the project's closing date. */
export function LiveTimeline({ f, closingDate }: { f: LiveForecast; closingDate?: string | null }) {
  const option = useMemo<EChartsOption | null>(() => {
    const today = t(f.asOf);
    const bars: { name: string; from: number; to: number; kind: "done" | "now" | "forecast" | "slow" }[] = [];
    const bid = f.stages.find((s) => s.stage === "bidding");
    const contract = f.stages.find((s) => s.stage === "contract");
    if (bid?.start) {
      if (bid.status === "done" && bid.end) bars.push({ name: "Bids & award", from: t(bid.start), to: t(bid.end), kind: "done" });
      else {
        bars.push({ name: "Bids & award", from: t(bid.start), to: today, kind: "now" });
        if (f.award) {
          bars.push({ name: "Bids & award", from: today, to: t(f.award.date), kind: "forecast" });
          bars.push({ name: "Bids & award", from: t(f.award.date), to: t(f.award.p90Date), kind: "slow" });
        }
      }
    }
    if (contract?.start && contract.end) {
      const s = t(contract.start), e = t(contract.end);
      if (contract.status === "forecast") bars.push({ name: "Contract", from: s, to: e, kind: "forecast" });
      else {
        bars.push({ name: "Contract", from: s, to: Math.min(e, today), kind: e < today ? "done" : "now" });
        if (e > today) bars.push({ name: "Contract", from: today, to: e, kind: "forecast" });
      }
    }
    if (!bars.length) return null;
    const accent = cssVar("--series-1", "#2a78d6");
    const muted = cssVar("--muted", "#888");
    const line = cssVar("--line", "#ddd");
    const style = { done: { color: accent, opacity: 1 }, now: { color: accent, opacity: 1 },
      forecast: { color: accent, opacity: 0.4 }, slow: { color: accent, opacity: 0.15 } };
    const rows = ["Bids & award", "Contract"];
    const marks = [{ xAxis: today, name: "today" }, ...(closingDate ? [{ xAxis: t(closingDate), name: "project closes" }] : [])];
    return {
      grid: { left: 96, right: 24, top: 28, bottom: 28 },
      tooltip: { trigger: "item", backgroundColor: cssVar("--surface", "#fff"), borderColor: line,
        textStyle: { color: cssVar("--foreground", "#222") },
        formatter: (p) => {
          const d = (p as unknown as { data: { label: string } }).data;
          return d.label;
        } },
      xAxis: { type: "time", axisLabel: { color: muted }, splitLine: { lineStyle: { color: line } } },
      yAxis: { type: "category", data: rows, inverse: true, axisLabel: { color: muted } },
      series: [{
        type: "custom",
        renderItem: (_params, api) => {
          const y = api.value(0) as number;
          const a = api.coord([api.value(1), y]);
          const b = api.coord([api.value(2), y]);
          const h = 18;
          return { type: "rect", shape: { x: a[0], y: a[1] - h / 2, width: Math.max(b[0] - a[0], 2), height: h, r: 3 },
            style: api.style() };
        },
        encode: { x: [1, 2], y: 0 },
        data: bars.map((b) => ({ value: [rows.indexOf(b.name), b.from, b.to], itemStyle: style[b.kind],
          label: `<b>${b.name}</b>: ${{ done: "done", now: "so far", forecast: "forecast", slow: "slow case (1 in 10 take longer)" }[b.kind]}<br/>` +
            `${new Date(b.from).toISOString().slice(0, 10)} to ${new Date(b.to).toISOString().slice(0, 10)} (${Math.round((b.to - b.from) / DAY)} days)` })),
        markLine: { symbol: "none", silent: true, data: marks, lineStyle: { color: muted, type: "dashed" },
          label: { formatter: "{b}", color: muted, fontSize: 10 } },
      }],
    } as EChartsOption;
  }, [f, closingDate]);
  const ref = useECharts(option);
  if (!option) return <p className="text-xs text-muted">No dates to draw: the tender date is not known.</p>;
  return <div ref={ref} className="h-40 w-full" role="img" aria-label="Package timeline: done, so far, and forecast" />;
}
