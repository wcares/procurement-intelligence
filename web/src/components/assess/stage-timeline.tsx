"use client";

import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { Precedent, RiskFlag, Stage } from "@/lib/api/types";
import { cssVar, useECharts } from "@/lib/use-echarts";

const LEVEL_VAR = { high: "--risk-high", medium: "--risk-medium", low: "--muted" } as const;

/** The tender's stages laid end to end at their typical length (and the slow case), with each risk marked on the stage
 * where it bites: colour = level, circle = historical statistic, diamond = model estimate. A marker click selects the
 * flag (the page scrolls to its evidence). Stages without dates in the data are listed, not drawn. */
export function StageTimeline({ stages, risks, precedents, onSelect }: { stages: Stage[]; risks: RiskFlag[]; precedents: Precedent[]; onSelect: (flagId: string) => void }) {
  const timed = useMemo(() => stages.filter((s) => s.median != null), [stages]);
  const untimed = stages.filter((s) => s.median == null);
  const lessons = (key: string) => precedents.filter((p) => p.stage === key).length;

  const option = useMemo<EChartsOption | null>(() => {
    if (!timed.length) return null;
    const shades = [cssVar("--accent", "#1f5fbf"), cssVar("--risk-medium", "#a15c07"), cssVar("--risk-low", "#1e7a46")];
    const muted = cssVar("--muted", "#888");
    const starts: Record<string, [number, number]> = {};
    let at = 0;
    for (const s of timed) {
      starts[s.key] = [at, at + (s.median as number)];
      at += s.median as number;
    }
    const total = at;
    const placed = risks.filter((r) => r.stage);
    const perStage: Record<string, number> = {};
    const markers = placed.map((r) => {
      const span = r.stage === "all" || !starts[r.stage!] ? [0, total] : starts[r.stage!];
      const k = (perStage[r.stage!] = (perStage[r.stage!] ?? 0) + 1);
      const x = span[0] + ((span[1] - span[0]) * k) / (placed.filter((p) => p.stage === r.stage).length + 1);
      return { value: [x, 2], id: r.id, label: r.label, detail: r.detail, symbol: r.basis === "model" ? "diamond" : "circle",
        itemStyle: { color: cssVar(LEVEL_VAR[r.level], "#888") } };
    });
    return {
      grid: { left: 130, right: 24, top: 10, bottom: 40 },
      tooltip: { trigger: "item", formatter: (p) => {
        const d = (p as unknown as { data: { label?: string; detail?: string; stage?: string; days?: number; n?: number; scope?: string; lessons?: number } }).data;
        if (d.label) return `<b>${d.label}</b><br/>${d.detail}`;
        return `<b>${d.stage}</b><br/>${Math.round(d.days ?? 0)} days · ${d.n} packages (${d.scope})${d.lessons ? `<br/>${d.lessons} past lesson${d.lessons === 1 ? "" : "s"} on this stage` : ""}`;
      } },
      xAxis: { type: "value", name: "days", nameLocation: "end", axisLabel: { color: muted }, splitLine: { lineStyle: { color: cssVar("--line", "#ddd") } } },
      yAxis: { type: "category", data: ["Typical", "Slow case (1 in 10)", "Risks"], inverse: true, axisLabel: { color: muted } },
      series: [
        ...timed.map((s, i) => ({
          type: "bar" as const, stack: "typical", barWidth: 22, name: s.label,
          itemStyle: { color: shades[i % shades.length] },
          // a name only where the segment has room (a 7-day signing stage beside 100+ days would overlap); the tooltip names all
          label: { show: (s.median as number) / total >= 0.15, position: "inside" as const, formatter: s.label.split(" ")[0], color: "#fff", fontSize: 11 },
          data: [{ value: s.median as number, stage: s.label, days: s.median, n: s.n, scope: s.scope,
            lessons: precedents.filter((p) => p.stage === s.key).length }, null, null],
        })),
        ...timed.map((s, i) => ({
          type: "bar" as const, stack: "slow", barWidth: 22, name: `${s.label} (slow)`,
          itemStyle: { color: shades[i % shades.length], opacity: 0.35 },
          data: [null, { value: (s.p90 ?? s.median) as number, stage: `${s.label}, slow case`, days: s.p90, n: s.n, scope: s.scope }, null],
        })),
        { type: "scatter" as const, symbolSize: 16, data: markers, z: 5 },
      ],
    } as EChartsOption;
  }, [timed, risks, precedents]);

  const ref = useECharts(option, (d) => {
    const id = (d as { id?: string }).id;
    if (id) onSelect(id);
  });

  return (
    <div>
      {option ? <div ref={ref} className="h-48 w-full" /> : <p className="text-sm text-muted">No dated stages for comparable packages.</p>}
      <p className="mt-1 text-xs text-muted">
        Stages end to end at their typical length for comparable packages; the faded row is the slow case (1 in 10 take longer).
        Markers are the risk flags on the stage where they bite (circle: historical statistic, diamond: model estimate); click one for its evidence.
        {untimed.length > 0 && ` Not drawn, no dates in the data: ${untimed.map((s) => s.label.toLowerCase()).join(", ")}`}
        {untimed.some((s) => lessons(s.key)) && ` (${untimed.reduce((n, s) => n + lessons(s.key), 0)} past lessons concern it).`}
      </p>
    </div>
  );
}
