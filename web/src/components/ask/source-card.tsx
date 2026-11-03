import { BarChart3, BookOpen, Calculator, ClipboardList, MessageSquare, Sparkles, TrendingUp } from "lucide-react";
import type { Provenance } from "@/lib/api/types";

const ICON: Record<Provenance["basis"][number]["kind"], typeof BookOpen> = {
  passages: BookOpen, assessment: Calculator, statistics: BarChart3, plan: ClipboardList, forecast: TrendingUp,
  conversation: MessageSquare, message: MessageSquare,
};

const KIND_LABEL: Record<string, string> = {
  evidence: "cited from the reports and checked",
  data: "from the engine's figures (every number checked)",
  plan: "about your plan (every number checked)",
  general: "the model's own guidance, not from the data",
};

/** The card under every chat reply saying where it came from: the model that wrote it (or that the engine composed
 * it), what it was built from, and how many sentences are evidence, engine data, plan or general guidance. A reply
 * with no cited passage still says what context it was generated from. */
export function SourceCard({ p }: { p: Provenance }) {
  const kinds = Object.entries(p.kinds).filter(([, n]) => n > 0);
  const cited = p.kinds.evidence ?? 0;
  const who = p.model ? `Written by ${p.model}` : "Composed by the engine";
  const how = cited && kinds.length === 1 ? ", every sentence cited" : cited ? ", partly cited" : p.model ? ", no passage cited" : "";
  return (
    <aside className="rounded-lg border border-line bg-subtle px-3 py-2.5 text-xs" aria-label="Where this answer came from">
      <p className="font-medium">
        <Sparkles size={12} className="mr-1 inline align-[-1px] text-brand-2" aria-hidden />
        {who}{how}
      </p>
      {p.basis.length > 0 && (
        <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-ink-muted">
          {p.basis.map((b, i) => {
            const Icon = ICON[b.kind] ?? BookOpen;
            return (
              <li key={i} className="flex items-start gap-1.5" title={b.detail}>
                <Icon size={12} className="mt-0.5 shrink-0" aria-hidden />
                <span><span className="text-foreground">{b.label}</span>{b.detail ? ` · ${b.detail}` : ""}</span>
              </li>
            );
          })}
        </ul>
      )}
      {kinds.length > 0 && (
        <p className="mt-1.5 text-ink-muted">
          {kinds.map(([k, n]) => `${n} sentence${n === 1 ? "" : "s"} ${KIND_LABEL[k] ?? k}`).join(" · ")}
        </p>
      )}
    </aside>
  );
}
