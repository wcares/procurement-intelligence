"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { DashboardResponse, DashRecords, HeatmapResponse, RankingResponse, RankingRow } from "@/lib/api/types";
import { Heatmap } from "@/components/dashboard/heatmap";
import { ProblemMix } from "@/components/dashboard/problem-mix";
import { ProblemTrend } from "@/components/dashboard/problem-trend";
import { RecentChangesCard } from "@/components/dashboard/recent-changes";
import { RankingTable } from "@/components/dashboard/ranking-table";
import { RecordsPanel } from "@/components/dashboard/records-panel";
import { SummaryCards } from "@/components/dashboard/summary-cards";
import { TrendChart } from "@/components/dashboard/trend-chart";

const box = "rounded-md border border-line bg-surface px-2 py-1 text-sm";

function Card({ title, children, note }: { title: string; children: React.ReactNode; note?: string }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {children}
      {note && <p className="mt-2 text-xs text-ink-muted">{note}</p>}
    </section>
  );
}

export function DashboardView() {
  const [dash, setDash] = useState<DashboardResponse | null>(null);
  const [measure, setMeasure] = useState("delay");
  const [group, setGroup] = useState("country");
  const [ranking, setRanking] = useState<RankingResponse | null>(null);
  const [heat, setHeat] = useState<HeatmapResponse | null>(null);
  const [heatMeasure, setHeatMeasure] = useState("delay");
  const [pick, setPick] = useState<{ title: string; key: string; group: string; measure: string; method?: string } | null>(null);
  const [records, setRecords] = useState<DashRecords | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.dashboard().then(setDash).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    api.ranking(measure, group).then(setRanking).catch((e: Error) => setError(e.message));
  }, [measure, group]);
  useEffect(() => {
    api.heatmap(heatMeasure).then(setHeat).catch((e: Error) => setError(e.message));
  }, [heatMeasure]);
  useEffect(() => {
    if (!pick) return;
    let live = true;
    api.records(pick.group, pick.key, pick.measure, pick.method).then((r) => live && setRecords(r)).catch((e: Error) => setError(e.message));
    return () => {
      live = false;
    };
  }, [pick]);

  const m = dash?.measures.find((x) => x.key === measure);
  const groups = m?.groups ?? ["country", "sector", "method"];
  const select = (p: NonNullable<typeof pick>) => {
    setRecords(null);
    setPick(p);
  };

  if (error) return <p className="rounded-lg bg-risk-high-soft px-4 py-3 text-sm text-risk-high">{error}</p>;
  if (!dash) return <p className="text-sm text-ink-muted">Loading…</p>;
  return (
    <div className="space-y-6">
      <SummaryCards s={dash.summary} />
      <RecentChangesCard />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Riskiest first" note={m?.note}>
          <div className="mb-3 flex flex-wrap gap-2">
            <select className={box} value={measure} onChange={(e) => { const next = dash.measures.find((x) => x.key === e.target.value); setMeasure(e.target.value); if (next?.groups && !next.groups.includes(group)) setGroup(next.groups[0]); }} aria-label="Measure">
              {dash.measures.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
            </select>
            <select className={box} value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Group by">
              {groups.map((g) => <option key={g} value={g}>by {dash.groups[g].toLowerCase()}</option>)}
            </select>
          </div>
          {ranking && <RankingTable data={ranking} selected={pick?.key ?? null}
            onSelect={(r: RankingRow) => select({ title: `${r.label}: ${ranking.measure.label.toLowerCase()}`, key: r.key, group: ranking.group, measure: ranking.measure.key })} />}
          <p className="mt-2 text-xs text-ink-muted">Greyed rows rest on fewer than {dash.fewProjects} projects. Click a row for its records.</p>
        </Card>
        <div className="space-y-6">
          {pick && <RecordsPanel title={pick.title} data={records} onClose={() => setPick(null)} />}
          <Card title="Award time over the years">
            <TrendChart t={dash.trends} />
          </Card>
        </div>
      </div>
      <Card title="Where it was slow: country by procurement method">
        <div className="mb-2">
          <select className={box} value={heatMeasure} onChange={(e) => setHeatMeasure(e.target.value)} aria-label="Heat map measure">
            {dash.measures.filter((x) => x.level === "package").map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
          </select>
        </div>
        {heat && <Heatmap data={heat} onSelect={(country, method, label) => select({ title: `${label} · ${method}: awarded packages`, key: country, group: "country", measure: heatMeasure, method })} />}
        <p className="text-xs text-ink-muted">Cells with fewer than {heat?.minN ?? 5} awards are left out. Click a cell for its packages.</p>
      </Card>
      <Card title="What the completion reports say went wrong">
        <div className="grid gap-6 lg:grid-cols-2">
          <ProblemMix mix={dash.problemMix} />
          <ProblemTrend rows={dash.trends.problems} few={dash.fewProjects} />
        </div>
      </Card>
    </div>
  );
}
