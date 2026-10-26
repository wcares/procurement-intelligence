"use client";

import { useState } from "react";
import { api } from "@/lib/api/client";
import type { AssessRequest, GoalResult } from "@/lib/api/types";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

/** Work backwards from a target: which method and how many lots met "awarded within N days" most often in the past. */
export function GoalPanel({ request }: { request: AssessRequest }) {
  const [days, setDays] = useState(90);
  const [lots, setLots] = useState(4);
  const [r, setR] = useState<GoalResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    setError(null);
    try {
      setR(await api.goal({ ...request, targetDays: days, maxLots: lots }));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div className="rounded-xl border border-line bg-surface p-5">
      <h3 className="mb-2 text-sm font-semibold text-ink-muted">Set a goal</h3>
      <div className="flex flex-wrap items-end gap-3 text-sm">
        <label className="text-xs">Awarded within (days)
          <input type="number" min={7} max={2000} value={days} onChange={(e) => setDays(Number(e.target.value))}
            className="ml-2 w-20 rounded border border-line bg-surface px-1 py-0.5" />
        </label>
        <label className="text-xs">up to
          <input type="number" min={1} max={10} value={lots} onChange={(e) => setLots(Number(e.target.value))}
            className="mx-1 w-12 rounded border border-line bg-surface px-1 py-0.5" /> lots
        </label>
        <button className="rounded-md border border-line px-3 py-1 text-xs" onClick={run}>Find set-ups</button>
      </div>
      {error && <p className="mt-2 text-xs text-risk-high">{error}</p>}
      {r && (
        <div className="mt-3 space-y-2">
          {r.note && <p className="text-xs text-ink-muted">{r.note}</p>}
          {r.options.length === 0 ? <p className="text-xs text-ink-muted">No method has enough comparable packages for this kind of purchase.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-ink-muted">
                  <tr><th className="py-1 pr-2">Method</th><th className="pr-2">Lots</th><th className="pr-2">Met the target</th>
                    <th className="pr-2">Median / 1 in 10</th><th className="pr-2">Based on</th><th>Check</th></tr>
                </thead>
                <tbody>
                  {r.options.map((o) => (
                    <tr key={`${o.method}-${o.lots}`} className="border-t border-line align-top">
                      <td className="py-1 pr-2">{o.methodLabel} ({o.method})</td>
                      <td className="pr-2">{o.lots}{o.lotValueUsd ? ` × ${usd.format(o.lotValueUsd)}` : ""}</td>
                      <td className="pr-2">
                        {o.share == null ? <span className="text-ink-muted">{o.note}</span> : (
                          <span className="inline-flex items-center gap-2">
                            <span className="inline-block h-2 w-16 rounded bg-subtle">
                              <span className="block h-2 rounded bg-brand" style={{ width: `${Math.round(o.share * 100)}%` }} />
                            </span>
                            {Math.round(o.share * 100)}%
                          </span>
                        )}
                      </td>
                      <td className="pr-2 tabular-nums">{o.medianDays != null ? `${o.medianDays} / ${o.p90Days} days` : "–"}</td>
                      <td className="pr-2 text-ink-muted">{o.n} packages · {o.scope}</td>
                      <td className="text-risk-medium">{o.flag ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {r.caveats.map((c, i) => <p key={i} className="text-xs text-ink-muted">{c}</p>)}
        </div>
      )}
    </div>
  );
}
