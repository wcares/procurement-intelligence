"use client";

import { useState } from "react";
import { BarChart3, BookOpen, Calculator, ChevronDown, ChevronRight, ClipboardList, MessageSquare, TrendingUp } from "lucide-react";
import type { Citation, Provenance } from "@/lib/api/types";

const ICON: Record<Provenance["basis"][number]["kind"], typeof BookOpen> = {
  passages: BookOpen, assessment: Calculator, statistics: BarChart3, plan: ClipboardList, forecast: TrendingUp,
  conversation: MessageSquare, message: MessageSquare,
};

/** The one line under an answer, in everyday words: what it rests on (quotes from project reports, figures from
 * past tenders, your plan) and whether AI wrote it. */
function summary(p: Provenance, citations: Citation[]): string {
  const reports = new Set(citations.map((c) => c.docId)).size;
  const has = (kind: string) => p.basis.some((b) => b.kind === kind);
  const parts: string[] = [];
  if (citations.length) parts.push(`${citations.length} quote${citations.length === 1 ? "" : "s"} from ${reports} project report${reports === 1 ? "" : "s"}`);
  if (has("statistics") || has("assessment") || has("forecast")) parts.push("figures from past tenders");
  if (!parts.length && has("plan")) parts.push("your plan");
  const what = parts.length ? `Sources: ${parts.join(" and ")}` : "No sources";
  const by = p.model ? "written by AI" : "not written by AI";
  const own = p.kinds.general ? `; ${p.kinds.general} sentence${p.kinds.general === 1 ? "" : "s"} ${p.kinds.general === 1 ? "is" : "are"} general advice` : "";
  return `${what} · ${by}${own}`;
}

/** The card under every chat reply, for planners: one line saying whether the answer has sources and who wrote it;
 * "Show sources" opens the cited passages (quote, report link), what the assistant looked up, and the technical
 * notes. Everything about where a reply came from lives here, nowhere else. */
export function SourceCard({ p, citations = [], steps, children, details, open: forced, onOpen }: {
  p: Provenance; citations?: Citation[]; steps?: string[]; children?: React.ReactNode; details?: React.ReactNode;
  /** controlled by the answer, which opens the card when a citation chip is clicked */
  open?: boolean; onOpen?: (open: boolean) => void;
}) {
  const [own, setOwn] = useState(false);
  const open = forced ?? own;
  const setOpen = (v: boolean) => { setOwn(v); onOpen?.(v); };
  const more = Boolean(children || steps?.length || details || p.basis.length);
  return (
    <aside className="rounded-lg border border-line bg-subtle text-xs" aria-label="Sources of this answer">
      <button type="button" onClick={() => more && setOpen(!open)} aria-expanded={open} disabled={!more}
        className="flex w-full items-center gap-2 px-3 py-2 text-left">
        {more ? (open ? <ChevronDown size={14} className="shrink-0 text-ink-muted" aria-hidden /> : <ChevronRight size={14} className="shrink-0 text-ink-muted" aria-hidden />) : <span className="w-3.5" />}
        <span className="min-w-0 flex-1">{summary(p, citations)}</span>
        {more && <span className="shrink-0 font-medium text-brand">{open ? "Hide sources" : "Show sources"}</span>}
      </button>
      {open && (
        <div className="space-y-4 border-t border-line px-3 py-3">
          {children && <div className="space-y-2">{children}</div>}
          {(p.basis.length > 0 || steps?.length) && (
            <div className="space-y-1.5">
              <p className="font-medium">What it used</p>
              <ul className="space-y-1 text-ink-muted">
                {p.basis.map((b, i) => {
                  const Icon = ICON[b.kind] ?? BookOpen;
                  return (
                    <li key={i} className="flex items-start gap-1.5">
                      <Icon size={12} className="mt-0.5 shrink-0" aria-hidden />
                      <span><span className="text-foreground">{b.label}</span>{b.detail ? ` · ${b.detail}` : ""}</span>
                    </li>
                  );
                })}
                {steps?.map((s, i) => <li key={`s${i}`} className="pl-[18px]">· {s}</li>)}
              </ul>
              {p.model && <p className="text-ink-muted">Written by AI ({p.model}). Each quoted sentence was checked against its source, and each figure against the data.</p>}
            </div>
          )}
          {details && <details className="text-ink-muted"><summary className="cursor-pointer">Technical notes</summary><div className="mt-2">{details}</div></details>}
        </div>
      )}
    </aside>
  );
}
