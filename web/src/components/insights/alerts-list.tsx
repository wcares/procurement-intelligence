"use client";

import type { Alert } from "@/lib/api/types";

const KIND: Record<Alert["kind"], string> = { new_notices: "new notices", reissued: "re-issued", awarded: "awards", report: "new report" };

/** Alerts newest first; each opens to the notices or reports behind it. */
export function AlertsList({ alerts, onRead, compact = false }: { alerts: Alert[]; onRead?: (id: string) => void; compact?: boolean }) {
  if (alerts.length === 0) return <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-ink-muted">No alerts yet. They appear after the next change detection that touches what you follow.</p>;
  return (
    <ul className={compact ? "space-y-2" : "grid gap-2.5 lg:grid-cols-2"}>
      {alerts.map((a) => (
        <li key={a.id} className={`rounded-xl border bg-subtle p-3.5 text-sm ${a.read ? "border-line" : "border-brand/60"}`}>
          <div className="flex flex-wrap items-baseline gap-x-2">
            {!a.read && <span className="size-2 rounded-full bg-brand" aria-label="unread" />}
            <span className="rounded-full bg-brand-soft px-2 text-xs text-brand">{KIND[a.kind]}</span>
            <span className="font-medium">{a.title}</span>
            <span className="ml-auto text-xs text-ink-muted">{new Date(a.at).toLocaleString()}</span>
          </div>
          <p className="mt-1 text-xs text-ink-muted">{a.detail}</p>
          {!compact && (
            <details className="mt-1" onToggle={(e) => (e.target as HTMLDetailsElement).open && !a.read && onRead?.(a.id)}>
              <summary className="cursor-pointer text-xs text-ink-muted">Evidence ({a.refs.length})</summary>
              <ul className="mt-1 space-y-0.5 border-l pl-3 text-xs">
                {a.refs.map((r) => (
                  <li key={r.key}>
                    <span className="font-mono text-ink-muted">{r.key}</span> {r.label}{r.days != null ? ` · ${r.days} days to award` : ""}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}
