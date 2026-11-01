import type { ReactNode } from "react";
import type { Citation, ResponseMeta, RiskLevel, TimelineBenchmark } from "@/lib/api/types";
import { API_BASE } from "@/lib/api/client";

const RISK_STYLE: Record<RiskLevel, string> = {
  high: "bg-risk-high-soft text-risk-high",
  medium: "bg-risk-medium-soft text-risk-medium",
  low: "bg-risk-low-soft text-risk-low",
};

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium capitalize ${RISK_STYLE[level]}`}>{level}</span>
  );
}

export function CitationCard({ c, index, highlight, action }: { c: Citation; index?: number; highlight?: string; action?: ReactNode }) {
  return (
    <article id={`cite-${c.id}`} className="rounded-lg border border-line bg-surface p-4">
      <header className="mb-2 flex flex-wrap items-baseline gap-x-2 text-xs text-ink-muted">
        {index !== undefined && <span className="font-mono font-semibold text-brand">[{index + 1}]</span>}
        <span className="font-medium text-foreground">{c.projectName}</span>
        <span>
          {c.projectId} · {c.countryCode}
        </span>
      </header>
      {c.imageUrl && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={`${API_BASE}${c.imageUrl}`} alt={c.section} loading="lazy" className="mb-2 max-h-80 max-w-full rounded border border-line bg-white" />
      )}
      {c.mediaUrl && (
        <div className="relative mb-2 inline-block">
          {c.mediaKind === "video" ? (
            <video src={`${API_BASE}${c.mediaUrl}`} controls preload="metadata" className="max-h-72 max-w-full rounded border border-line" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={`${API_BASE}${c.mediaUrl}`} alt={c.section} loading="lazy" className="max-h-72 max-w-full rounded border border-line" />
          )}
          {c.synthetic && (
            <span className="absolute left-1 top-1 rounded bg-risk-medium px-1.5 py-0.5 text-[10px] font-semibold uppercase text-white">Synthetic demo</span>
          )}
        </div>
      )}
      {c.kind === "grid" ? (
        <MarkdownTable text={c.quote} />
      ) : (
        <blockquote className="border-l-2 border-brand pl-3 text-sm leading-relaxed whitespace-pre-line">
          {highlight ? <Highlighted text={c.quote} needle={highlight} /> : c.quote}
        </blockquote>
      )}
      <footer className="mt-2 flex flex-wrap items-center gap-x-1 text-xs text-ink-muted">
        {c.docType} · <span className="italic">{c.section}</span>
        {c.url && (
          <>
            {" "}·{" "}
            <a href={c.url} target="_blank" rel="noreferrer" className="text-brand underline-offset-2 hover:underline">
              open source PDF
            </a>
          </>
        )}
        {action && <span className="ml-auto">{action}</span>}
      </footer>
    </article>
  );
}

/** A table passage (markdown rows) as a table; a caption line above the first row is shown above it. */
function MarkdownTable({ text }: { text: string }) {
  const lines = text.split("\n");
  const first = lines.findIndex((l) => l.startsWith("|"));
  const caption = lines.slice(0, Math.max(first, 0)).join(" ").trim();
  const rows = lines.slice(Math.max(first, 0)).filter((l) => l.startsWith("|") && !/^\|[-| ]+\|$/.test(l))
    .map((l) => l.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
  if (!rows.length) return <blockquote className="border-l-2 border-brand pl-3 text-sm">{text}</blockquote>;
  return (
    <div>
      {caption && <p className="mb-1 text-sm font-medium">{caption}</p>}
      <div className="max-h-72 overflow-auto rounded border border-line">
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 bg-subtle">
            <tr>{rows[0].map((c, j) => <th key={j} className="border-b border-line px-2 py-1 text-left font-medium">{c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(1).map((r, i) => (
              <tr key={i} className="odd:bg-background">{r.map((c, j) => <td key={j} className="border-b border-line px-2 py-1 align-top">{c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Highlighted({ text, needle }: { text: string; needle: string }) {
  const i = text.indexOf(needle);
  if (i < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded bg-brand-soft px-0.5 text-foreground">{needle}</mark>
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
        <span className="text-ink-muted">days, median tender notice → award</span>
      </div>
      <div className="relative mt-5 h-8" role="img" aria-label={`Middle half ${Math.round(t.p25)} to ${Math.round(t.p75)} days, median ${Math.round(t.median)}, 90th percentile ${Math.round(t.p90)}`}>
        <div className="absolute top-3.5 h-1 w-full rounded bg-subtle" />
        <div className="absolute top-2 h-4 rounded bg-brand-soft" style={{ left: pct(t.p25), width: pct(t.p75 - t.p25) }} />
        <div className="absolute top-0 h-8 w-0.5 bg-brand" style={{ left: pct(t.median) }} />
        <div className="absolute top-1.5 h-5 w-0.5 bg-risk-high" style={{ left: pct(t.p90) }} />
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <Stat label="Middle half" value={`${Math.round(t.p25)}–${Math.round(t.p75)} d`} />
        <Stat label="Slowest 10% over" value={`${Math.round(t.p90)} d`} tone="text-risk-high" />
        <Stat label="Based on" value={`${t.n} packages`} />
      </dl>
      <p className="mt-2 text-xs text-ink-muted">Comparison set: {t.scope}.</p>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className={`font-medium tabular-nums ${tone ?? ""}`}>{value}</dd>
    </div>
  );
}

export function Caveats({ meta }: { meta: ResponseMeta }) {
  if (!meta.caveats.length) return null;
  return (
    <aside className="rounded-lg border border-dashed border-line px-4 py-3 text-xs text-ink-muted">
      {meta.source === "mock" && <span className="mr-1 rounded bg-subtle px-1.5 py-0.5 font-mono font-semibold">MOCK</span>}
      {meta.caveats.join(" ")}
    </aside>
  );
}
