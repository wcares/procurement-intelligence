import type { DashboardResponse } from "@/lib/api/types";

/** Headline numbers: what the dashboard covers and how procurement went overall. */
export function SummaryCards({ s }: { s: DashboardResponse["summary"] }) {
  const cards = [
    { label: "Projects with a completion report", value: `${s.projects}`, sub: `${s.countries} countries` },
    { label: "Procurement packages", value: s.packages.toLocaleString(), sub: `${s.awarded.toLocaleString()} with a known award time` },
    { label: "Median tender to award", value: s.median_days == null ? "–" : `${Math.round(s.median_days)} days`, sub: "awarded packages" },
    { label: "Awards over 6 months", value: s.long_share == null ? "–" : `${Math.round(s.long_share * 100)}%`, sub: "of awarded packages" },
    { label: "Projects with re-tendering", value: `${s.rebid_projects}`, sub: `${s.amendment_projects} with contract amendments` },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-line bg-surface p-4">
          <p className="text-xs text-muted">{c.label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums">{c.value}</p>
          <p className="text-xs text-muted">{c.sub}</p>
        </div>
      ))}
    </div>
  );
}
