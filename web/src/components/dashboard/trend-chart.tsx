"use client";

import { Bar, CartesianGrid, ComposedChart, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DashboardResponse } from "@/lib/api/types";

/** Award time by tender year; years after the follow-up line are shaded as incomplete. */
export function TrendChart({ t }: { t: DashboardResponse["trends"] }) {
  const data = t.award.map((a) => ({ ...a, long_pct: Math.round(a.long_share * 100) }));
  const last = data.length ? data[data.length - 1].year : t.completeUntil;
  return (
    <div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="year" stroke="var(--muted)" fontSize={12} />
            <YAxis yAxisId="days" stroke="var(--muted)" fontSize={12} />
            <YAxis yAxisId="n" orientation="right" stroke="var(--muted)" fontSize={12} />
            <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", fontSize: 12 }}
              formatter={(v, name) => [v, name === "median_days" ? "median days" : name === "n" ? "awards" : "over 6 months (%)"]} />
            {last > t.completeUntil && (
              <ReferenceArea yAxisId="days" x1={t.completeUntil + 1} x2={last} fill="var(--subtle)" fillOpacity={0.8} label={{ value: "incomplete", fontSize: 11, fill: "var(--muted)" }} />
            )}
            <Bar yAxisId="n" dataKey="n" fill="var(--line)" barSize={18} />
            <Line yAxisId="days" dataKey="median_days" stroke="var(--accent)" strokeWidth={2} dot />
            <Line yAxisId="days" dataKey="long_pct" stroke="var(--risk-high)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-muted">
        Blue: median days from tender to award, by tender year. Red dashed: % over 6 months. Grey bars: awards counted. {t.note}
      </p>
    </div>
  );
}
