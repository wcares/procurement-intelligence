"use client";

import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import type { Precedent, Prediction, RiskFlag, Stage } from "@/lib/api/types";
import { cssVar, useECharts } from "@/lib/use-echarts";

const LEVEL_VAR = { high: "--risk-high", medium: "--risk-medium", low: "--muted" } as const;

/** The tender's stages laid end to end at their typical length (and the slow case), with each risk marked on the stage
 * where it bites: colour = level, circle = historical statistic, diamond = model estimate. A marker click selects the
 * flag (the page scrolls to its evidence). A third row is this package's own estimate: the predicted time from tender to
 * award (model or historical median) in place of the typical bidding stage, faded to its slow case, then the typical
 * signing and contract stages. A fourth row places the past lessons (precedent passages) on the stage they
 * concern; a click scrolls to the passage. onSelect gets the element id to show. Stages without dates in the data are
 * listed, not drawn. */
export function StageTimeline({ stages, risks, precedents, prediction, onSelect }: { stages: Stage[]; risks: RiskFlag[]; precedents: Precedent[]; prediction?: Prediction | null; onSelect: (elementId: string) => void }) {
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
    // spread the items of one stage evenly across its segment ("all" or an undrawn stage: the whole timeline)
    const spread = <T extends { stage?: string | null }>(items: T[]) => {
      const seen: Record<string, number> = {};
      return items.map((it) => {
        const span = !starts[it.stage!] ? [0, total] : starts[it.stage!];
        const k = (seen[it.stage!] = (seen[it.stage!] ?? 0) + 1);
        return span[0] + ((span[1] - span[0]) * k) / (items.filter((o) => o.stage === it.stage).length + 1);
      });
    };
    const placed = risks.filter((r) => r.stage);
    const markers = spread(placed).map((x, i) => {
      const r = placed[i];
      return { value: [x, 3], target: `flag-${r.id}`, label: r.label, detail: r.detail, symbol: r.basis === "model" ? "diamond" : "circle",
        itemStyle: { color: cssVar(LEVEL_VAR[r.level], "#888") } };
    });
    const staged = precedents.filter((p) => p.stage);
    const lessonMarks = spread(staged).map((x, i) => {
      const p = staged[i];
      return { value: [x, 4], target: `cite-${p.citation.id}`, label: `Lesson: ${p.citation.projectName}`,
        detail: `${p.citation.quote.slice(0, 160)}…`, symbol: "rect", itemStyle: { color: muted } };
    });
    return {
      grid: { left: 130, right: 24, top: 10, bottom: 40 },
      tooltip: { trigger: "item", formatter: (p) => {
        const d = (p as unknown as { data: { label?: string; detail?: string; stage?: string; days?: number; n?: number | null; scope?: string; lessons?: number } }).data;
        if (d.label) return `<b>${d.label}</b><br/>${d.detail}`;
        return `<b>${d.stage}</b><br/>${Math.round(d.days ?? 0)} days · ${d.n != null ? `${d.n} packages ` : ""}(${d.scope})${d.lessons ? `<br/>${d.lessons} past lesson${d.lessons === 1 ? "" : "s"} on this stage` : ""}`;
      } },
      xAxis: { type: "value", name: "days", nameLocation: "end", axisLabel: { color: muted }, splitLine: { lineStyle: { color: cssVar("--line", "#ddd") } } },
      yAxis: { type: "category", data: ["Typical", "Slow case (1 in 10)", "This package (estimate)", "Risks", "Past lessons"], inverse: true, axisLabel: { color: muted } },
      series: [
        ...timed.map((s, i) => ({
          type: "bar" as const, stack: "typical", barWidth: 22, name: s.label,
          itemStyle: { color: shades[i % shades.length] },
          // a name only where the segment has room (a 7-day signing stage beside 100+ days would overlap); the tooltip names all
          label: { show: (s.median as number) / total >= 0.15, position: "inside" as const, formatter: s.label.split(" ")[0], color: "#fff", fontSize: 11 },
          data: [{ value: s.median as number, stage: s.label, days: s.median, n: s.n, scope: s.scope,
            lessons: precedents.filter((p) => p.stage === s.key).length }, null, null, null, null],
        })),
        ...timed.map((s, i) => ({
          type: "bar" as const, stack: "slow", barWidth: 22, name: `${s.label} (slow)`,
          itemStyle: { color: shades[i % shades.length], opacity: 0.35 },
          data: [null, { value: (s.p90 ?? s.median) as number, stage: `${s.label}, slow case`, days: s.p90, n: s.n, scope: s.scope }, null, null, null],
        })),
        ...estimateBars(timed, prediction, shades),
        { type: "scatter" as const, symbolSize: 16, data: markers, z: 5 },
        { type: "scatter" as const, symbolSize: 11, data: lessonMarks, z: 5 },
      ],
    } as EChartsOption;
  }, [timed, risks, precedents, prediction]);

  const ref = useECharts(option, (d) => {
    const target = (d as { target?: string }).target;
    if (target) onSelect(target);
  });

  return (
    <div>
      {option ? <div ref={ref} className="h-64 w-full" /> : <p className="text-sm text-muted">No dated stages for comparable packages.</p>}
      <p className="mt-1 text-xs text-muted">
        Stages end to end at their typical length for comparable packages; the faded row is the slow case (1 in 10 take longer).
        Markers are the risk flags on the stage where they bite (circle: historical statistic, diamond: model estimate); click one for its evidence. Squares are past lessons on that stage; click one for the passage.
        {prediction && ` "This package": ${prediction.days_p50} days from tender to award (${prediction.basis === "model" ? "model estimate" : "historical median"}), faded to ${prediction.days_p90 ?? "–"} days in the slow case${prediction.p90_basis === "historical" && prediction.basis === "model" ? " (historical: the model did not beat it there)" : ""}, then the typical signing and contract stages.`}
        {untimed.length > 0 && ` Not drawn, no dates in the data: ${untimed.map((s) => s.label.toLowerCase()).join(", ")}`}
        {untimed.some((s) => lessons(s.key)) && ` (${untimed.reduce((n, s) => n + lessons(s.key), 0)} past lessons concern it).`}
      </p>
    </div>
  );
}


/** The estimate row: the bidding stage replaced by this package's predicted tender-to-award time and its slow case, the
 * later stages at their typical length. Nothing when there is no prediction or no timed bidding stage. */
function estimateBars(timed: Stage[], prediction: Prediction | null | undefined, shades: string[]) {
  const bid = timed.findIndex((s) => s.key === "bidding");
  if (!prediction || bid < 0) return [];
  const row = (v: number | null, extra: object) => [null, null, v == null ? null : { value: v, ...extra }, null, null];
  const label = prediction.basis === "model" ? "model estimate" : "historical median";
  const out = [];
  for (const [i, s] of timed.entries()) {
    if (i === bid) {
      out.push({ type: "bar" as const, stack: "estimate", barWidth: 22, name: "This package",
        itemStyle: { color: shades[i % shades.length], borderColor: cssVar("--foreground", "#222"), borderWidth: 1 },
        label: { show: true, position: "inside" as const, formatter: `${prediction.days_p50} d`, color: "#fff", fontSize: 11 },
        data: row(prediction.days_p50, { stage: `${s.label}: this package`, days: prediction.days_p50, n: null, scope: label }) });
      const slow = prediction.days_p90 != null ? prediction.days_p90 - prediction.days_p50 : 0;
      if (slow > 0) {
        out.push({ type: "bar" as const, stack: "estimate", barWidth: 22, name: "This package (slow case)",
          itemStyle: { color: shades[i % shades.length], opacity: 0.35 },
          data: row(slow, { stage: `${s.label}: this package, slow case`, days: prediction.days_p90, n: null,
            scope: prediction.p90_basis === "model" ? "model" : "historical 90th percentile" }) });
      }
    } else if (i > bid) {
      out.push({ type: "bar" as const, stack: "estimate", barWidth: 22, name: `${s.label} (typical)`,
        itemStyle: { color: shades[i % shades.length], opacity: 0.6 },
        data: row(s.median as number, { stage: `${s.label} (typical)`, days: s.median, n: s.n, scope: s.scope }) });
    }
  }
  return out;
}
