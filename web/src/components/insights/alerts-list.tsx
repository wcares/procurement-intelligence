"use client";

import type { Alert } from "@/lib/api/types";

const KIND: Record<Alert["kind"], string> = { new_notices: "new notices", reissued: "re-issued", awarded: "awards", report: "new report" };

/** Alerts newest first; each opens to the notices or reports behind it. */
export function AlertsList({ alerts, onRead, compact = false }: { alerts: Alert[]; onRead?: (id: string) => void; compact?: boolean }) {
  if (alerts.length === 0) return <p className="text-xs text-muted">No alerts yet.</p>;
  return (
    <ul className="space-y-2">
      {alerts.map((a) => (
        <li key={a.id} className={`rounded-lg border bg-surface p-3 text-sm ${a.read ? "border-line" : "border-accent"}`}>
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="rounded bg-subtle px-1.5 text-xs">{KIND[a.kind]}</span>
            <span className="font-medium">{a.title}</span>
            <span className="ml-auto text-xs text-muted">{new Date(a.at).toLocaleString()}</span>
          </div>
          <p className="mt-1 text-xs text-muted">{a.detail}</p>
          {!compact && (
            <details className="mt-1" onToggle={(e) => (e.target as HTMLDetailsElement).open && !a.read && onRead?.(a.id)}>
              <summary className="cursor-pointer text-xs text-muted">Evidence ({a.refs.length})</summary>
              <ul className="mt-1 space-y-0.5 border-l pl-3 text-xs">
                {a.refs.map((r) => (
                  <li key={r.key}>
                    <span className="font-mono text-muted">{r.key}</span> {r.label}{r.days != null ? ` · ${r.days} days to award` : ""}
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
