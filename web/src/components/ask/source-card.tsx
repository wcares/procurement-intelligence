"use client";

import { useState } from "react";
import { BarChart3, BookOpen, Calculator, ChevronDown, ChevronRight, ClipboardList, MessageSquare, TrendingUp } from "lucide-react";
import type { Citation, Provenance } from "@/lib/api/types";

const ICON: Record<Provenance["basis"][number]["kind"], typeof BookOpen> = {
  passages: BookOpen, assessment: Calculator, statistics: BarChart3, plan: ClipboardList, forecast: TrendingUp,
  conversation: MessageSquare, message: MessageSquare,
};

/** The one line under an answer saying whether it has sources: "Backed by 3 passages from 2 reports and the
 * engine's figures", plus who wrote it. */
function summary(p: Provenance, citations: Citation[]): string {
  const reports = new Set(citations.map((c) => c.docId)).size;
  const figures = p.basis.filter((b) => b.kind === "assessment" || b.kind === "statistics" || b.kind === "forecast").length;
  const parts: string[] = [];
  if (citations.length) parts.push(`${citations.length} passage${citations.length === 1 ? "" : "s"} from ${reports} report${reports === 1 ? "" : "s"}`);
  if (figures) parts.push(`the engine's figures (${figures})`);
  const plan = p.basis.some((b) => b.kind === "plan");
  if (plan && !parts.length) parts.push("your plan");
  const backed = parts.length ? `Backed by ${parts.join(" and ")}` : "No source cited";
  const by = p.model ? "written by the AI assistant" : "composed by the engine, no model involved";
  const own = p.kinds.general ? `; ${p.kinds.general} sentence${p.kinds.general === 1 ? "" : "s"} of general guidance` : "";
  return `${backed} · ${by}${own}`;
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
              <p className="font-medium">What the assistant used</p>
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
              {p.model && <p className="text-ink-muted">Written by {p.model}; every cited sentence was checked against its passage, and every figure against the engine&apos;s data.</p>}
            </div>
          )}
          {details && <details className="text-ink-muted"><summary className="cursor-pointer">Technical notes</summary><div className="mt-2">{details}</div></details>}
        </div>
      )}
    </aside>
  );
}
