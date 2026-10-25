import type { ReactNode } from "react";
import type { Citation, ResponseMeta, RiskLevel, TimelineBenchmark } from "@/lib/api/types";

const RISK_STYLE: Record<RiskLevel, string> = {
  high: "bg-risk-high-soft text-risk-high",
  medium: "bg-risk-medium-soft text-risk-medium",
  low: "bg-risk-low-soft text-risk-low",
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${RISK_STYLE[level]}`}>{level}</span>
  );
}

export function CitationCard({ c, index, highlight, action }: { c: Citation; index?: number; highlight?: string; action?: ReactNode }) {
  return (
    <article id={`cite-${c.id}`} className="rounded-lg border border-line bg-surface p-4">
      <header className="mb-2 flex flex-wrap items-baseline gap-x-2 text-xs text-muted">
        {index !== undefined && <span className="font-mono font-semibold text-accent">[{index + 1}]</span>}
        <span className="font-medium text-foreground">{c.projectName}</span>
        <span>
          {c.projectId} · {c.countryCode}
        </span>
      </header>
      <blockquote className="border-l-2 border-accent pl-3 text-sm leading-relaxed">
        {highlight ? <Highlighted text={c.quote} needle={highlight} /> : c.quote}
      </blockquote>
      <footer className="mt-2 flex flex-wrap items-center gap-x-1 text-xs text-muted">
        {c.docType} · <span className="italic">{c.section}</span> ·{" "}
        <a href={c.url} target="_blank" rel="noreferrer" className="text-accent underline-offset-2 hover:underline">
          open source PDF
        </a>
        {action && <span className="ml-auto">{action}</span>}
      </footer>
    </article>
  );
}

function Highlighted({ text, needle }: { text: string; needle: string }) {
  const i = text.indexOf(needle);
  if (i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded bg-accent-soft px-0.5 text-foreground">{needle}</mark>
      {text.slice(i + needle.length)}
    </>
  );
}

/** Interquartile range bar with median and 90th percentile, on a 0..max-days axis. */
export function TimelineBar({ t }: { t: TimelineBenchmark }) {
  const max = Math.max(t.p90 * 1.1, 30);
  const pct = (d: number) => `${(d / max) * 100}%`;
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-semibold tabular-nums">{Math.round(t.median)}</span>
        <span className="text-muted">days, median tender notice → award</span>
      </div>
      <div className="relative mt-5 h-8" role="img" aria-label={`Middle half ${Math.round(t.p25)} to ${Math.round(t.p75)} days, median ${Math.round(t.median)}, 90th percentile ${Math.round(t.p90)}`}>
        <div className="absolute top-3.5 h-1 w-full rounded bg-subtle" />
        <div className="absolute top-2 h-4 rounded bg-accent-soft" style={{ left: pct(t.p25), width: pct(t.p75 - t.p25) }} />
        <div className="absolute top-0 h-8 w-0.5 bg-accent" style={{ left: pct(t.median) }} />
        <div className="absolute top-1.5 h-5 w-0.5 bg-risk-high" style={{ left: pct(t.p90) }} />
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <Stat label="Middle half" value={`${Math.round(t.p25)}–${Math.round(t.p75)} d`} />
        <Stat label="Slowest 10% over" value={`${Math.round(t.p90)} d`} tone="text-risk-high" />
        <Stat label="Based on" value={`${t.n} packages`} />
      </dl>
      <p className="mt-2 text-xs text-muted">Comparison set: {t.scope}.</p>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`font-medium tabular-nums ${tone ?? ""}`}>{value}</dd>
    </div>
  );
}

export function Caveats({ meta }: { meta: ResponseMeta }) {
  if (!meta.caveats.length) return null;
  return (
    <aside className="rounded-lg border border-dashed border-line px-4 py-3 text-xs text-muted">
      {meta.source === "mock" && <span className="mr-1 rounded bg-subtle px-1.5 py-0.5 font-mono font-semibold">MOCK</span>}
      {meta.caveats.join(" ")}
    </aside>
  );
}
