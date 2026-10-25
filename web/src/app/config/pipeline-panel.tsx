"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { PipelineResponse } from "@/lib/api/types";

const when = (iso: string) => new Date(iso).toLocaleString();

export function Pipeline() {
  const [data, setData] = useState<PipelineResponse | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    api.pipeline().then(setData).catch(() => setData(null));
  }, []);

  async function detect() {
    try {
      const r = await api.detectNow();
      setNote(r.queued ? "Detection queued; it runs when the app is idle." : r.note);
    } catch (e) {
      setNote((e as Error).message);
    }
  }

  if (!data) return null;
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Change detection</h2>
      <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
        <p className="text-xs text-muted">
          Each source is checked on its interval; only what changed is processed, by the rules below. The weekly refresh
          still rebuilds everything as a reconciliation.
        </p>
        <table className="w-full text-left text-xs">
          <thead className="text-muted">
            <tr><th>Data</th><th>Tracked</th><th>Checked every</th><th>Last check</th><th>Changes</th></tr>
          </thead>
          <tbody>
            {data.entityTypes.map((e) => {
              const last = data.lastRun[e.name];
              return (
                <tr key={e.name} className="border-t border-line">
                  <td className="py-1 font-medium">{e.name}</td>
                  <td className="tabular-nums">{data.tracked[e.name] ?? 0}</td>
                  <td>{e.every}</td>
                  <td>{last ? when(last.ranAt) : "not yet"}</td>
                  <td className="tabular-nums">{last ? last.events : "–"}{last?.note ? <span className="text-muted"> · {last.note}</span> : null}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <button className="rounded-md border border-line px-2 py-1 text-xs" onClick={detect}>Check all sources now</button>
        {note && <p className="text-xs text-muted">{note}</p>}
        <details className="text-xs">
          <summary className="cursor-pointer">Rules ({data.rules.length})</summary>
          <ul className="mt-1 space-y-0.5">
            {data.rules.map((r) => (
              <li key={r.id}>
                <span className="font-mono">{r.on.join(", ")}</span>
                {r.fields.length > 0 && <span className="text-muted"> (fields: {r.fields.join(", ")})</span>} → {r.do.join(", ")}
              </li>
            ))}
          </ul>
        </details>
        <div>
          <h3 className="text-xs font-semibold">Recent rule firings</h3>
          {data.firings.length === 0 ? <p className="text-xs text-muted">None yet.</p> : (
            <ul className="text-xs">
              {data.firings.slice(0, 10).map((f) => (
                <li key={`${f.batch}:${f.rule}`}>{when(f.firedAt)} · {f.rule} · {f.events} event{f.events === 1 ? "" : "s"} → {f.actions.join(", ")}</li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-xs font-semibold">Recent changes</h3>
          {data.events.length === 0 ? <p className="text-xs text-muted">None yet.</p> : (
            <ul className="text-xs">
              {data.events.slice(0, 15).map((e, i) => (
                <li key={`${e.batch}:${e.type}:${e.key}:${i}`}>
                  {when(e.detectedAt)} · <span className="font-mono">{e.type}</span> {e.key !== "all" && e.key}
                  {e.changed.length > 0 && <span className="text-muted"> ({e.changed.join(", ")})</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
