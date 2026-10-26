"use client";

import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DashboardResponse } from "@/lib/api/types";

/** How often each kind of problem is reported in the completion reports (with the reliability caution). */
export function ProblemMix({ mix }: { mix: DashboardResponse["problemMix"] }) {
  return (
    <div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={mix.kinds} layout="vertical" margin={{ left: 8, right: 16 }}>
            <XAxis type="number" stroke="var(--ink-muted)" fontSize={12} />
            <YAxis type="category" dataKey="kind" width={210} stroke="var(--ink-muted)" fontSize={11} />
            <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", fontSize: 12 }} formatter={(v) => [v, "passages"]} />
            <Bar dataKey="passages" fill="var(--brand)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-ink-muted">{mix.note}</p>
    </div>
  );
}
