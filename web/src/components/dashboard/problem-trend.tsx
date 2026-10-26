"use client";

import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DashboardResponse } from "@/lib/api/types";

/** Problem passages per completion report, by the project's closing year; years behind few reports are greyed. */
export function ProblemTrend({ rows, few }: { rows: DashboardResponse["trends"]["problems"]; few: number }) {
  if (rows.length === 0) return <p className="text-sm text-ink-muted">No tagged completion reports yet.</p>;
  return (
    <div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 16, right: 8, bottom: 0, left: -16 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="year" stroke="var(--ink-muted)" fontSize={12} />
            <YAxis stroke="var(--ink-muted)" fontSize={12} />
            <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", fontSize: 12 }}
              cursor={{ fill: "var(--subtle)" }}
              formatter={(v, _n, item) => [`${v} per report (${item.payload.projects} report${item.payload.projects === 1 ? "" : "s"})`, "problem passages"]} />
            <Bar dataKey="per_project" radius={[4, 4, 0, 0]} maxBarSize={40}>
              {rows.map((r) => <Cell key={r.year} fill={r.projects < few ? "var(--line)" : "var(--brand)"} />)}
              <LabelList dataKey="projects" position="top" fontSize={11} fill="var(--ink-muted)" formatter={(v) => `n=${v}`} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        Problem passages per completion report, by the year the project closed; n = reports. Grey bars rest on fewer than
        {" "}{few} reports.
      </p>
    </div>
  );
}
