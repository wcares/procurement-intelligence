"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { EventBatch } from "@/lib/api/types";
import { when } from "./when";

const STATUS_CLASS: Record<string, string> = { done: "text-risk-low", failed: "text-risk-high", running: "text-brand" };

/** Detection batches newest first: what changed, the rules that fired, the job they queued and what it ran. Filter by
 * data type or event type; older batches load on request. */
export function EventLogView() {
  const [type, setType] = useState("");
  const [types, setTypes] = useState<string[]>([]);
  const [batches, setBatches] = useState<EventBatch[] | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((filter: string, before?: string) => api.events(filter || undefined, before).then((r) => {
    setTypes((t) => (t.length ? t : r.types));
    setBatches((b) => (before && b ? [...b, ...r.batches] : r.batches));
    setMore(r.more);
  }).catch((e) => setError((e as Error).message)), []);
  useEffect(() => {
    load("");
  }, [load]);
  const choose = (t: string) => {
    setType(t);
    setBatches(null);
    load(t);
  };

  const entityTypes = [...new Set(types.map((t) => t.split(".")[0]))];
  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  return (
    <div className="space-y-4">
      <label className="flex items-center gap-2 text-sm">
        <span className="text-ink-muted">Show</span>
        <select className="rounded-md border border-line bg-surface px-2 py-1" value={type} onChange={(e) => choose(e.target.value)}>
          <option value="">all events</option>
          {entityTypes.map((t) => (
            <optgroup key={t} label={t}>
              <option value={t}>all {t}</option>
              {types.filter((x) => x.startsWith(`${t}.`)).map((x) => <option key={x} value={x}>{x}</option>)}
            </optgroup>
          ))}
        </select>
      </label>
      {batches === null ? <p className="text-sm text-ink-muted">Loading…</p> : batches.length === 0 ? (
        <p className="text-sm text-ink-muted">No events{type ? ` of type ${type}` : ""} yet.</p>
      ) : (
        <ol className="space-y-3">{batches.map((b) => <Batch key={b.batch} b={b} />)}</ol>
      )}
      {more && batches && (
        <button className="rounded-md border border-line px-3 py-1.5 text-sm" onClick={() => load(type, batches[batches.length - 1].at)}>Older batches</button>
      )}
    </div>
  );
}

function Batch({ b }: { b: EventBatch }) {
  const total = Object.values(b.counts).reduce((a, n) => a + n, 0);
  return (
    <li className="rounded-xl border border-line bg-surface p-4 text-sm">
      <header className="mb-2 flex flex-wrap items-baseline gap-x-3">
        <span className="font-semibold">{when(b.at)}</span>
        <span className="font-mono text-xs text-ink-muted">{b.batch}</span>
        <span className="text-xs text-ink-muted">{Object.entries(b.counts).map(([t, n]) => `${n} ${t}`).join(" · ")}</span>
      </header>
      {b.firings.length > 0 ? (
        <ul className="mb-2 space-y-1 text-xs">
          {b.firings.map((f) => (
            <li key={f.rule}>
              Rule <span className="font-medium">{f.rule}</span> ({f.events} event{f.events === 1 ? "" : "s"}) → {f.actions.join(", ")}
              {f.job && (
                <span> · job <span className="font-mono">{f.job}</span>{" "}
                  {f.jobStatus ? <span className={STATUS_CLASS[f.jobStatus.status] ?? "text-ink-muted"}>{f.jobStatus.status}</span> : <span className="text-ink-muted">(no longer kept)</span>}
                  {f.jobStatus?.error && <span className="text-ink-muted">: {f.jobStatus.error}</span>}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : <p className="mb-2 text-xs text-ink-muted">No rule fired (a reconciliation after a full refresh, or only derived events).</p>}
      {b.actionsRun.length > 0 && (
        <p className="mb-2 text-xs"><span className="text-ink-muted">Ran:</span> {b.actionsRun.map((a) => `${a.action}${a.outcome === "ran" ? "" : ` (${a.outcome})`}`).join(" → ")}</p>
      )}
      <details>
        <summary className="cursor-pointer text-xs text-ink-muted">Events ({b.events.length < total ? `${b.events.length} of ${total}` : b.events.length})</summary>
        <ul className="mt-1 max-h-64 overflow-auto text-xs">
          {b.events.map((e, i) => (
            <li key={`${e.type}:${e.key}:${i}`}>
              <span className="font-mono">{e.type}</span> {e.key !== "all" && e.key}
              {e.changed.length > 0 && <span className="text-ink-muted"> ({e.changed.join(", ")})</span>}
            </li>
          ))}
        </ul>
      </details>
    </li>
  );
}
