"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Connector, ConnectorsResponse } from "@/lib/api/types";
import { relative, when } from "./when";

/** Each source: how it reaches us (mode), what the next read asks for (cursor), the last success and last error, and
 * when it is read next (later after failures: it backs off). A read can be queued now. */
export function ConnectorsView() {
  const [data, setData] = useState<ConnectorsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const load = useCallback(() => api.connectors().then(setData).catch((e) => setError((e as Error).message)), []);
  useEffect(() => {
    load();
  }, [load]);

  async function readNow(types?: string) {
    try {
      const r = await api.detectNow(types);
      setNote(r.queued ? `Read of ${types ?? "every source"} queued; it runs when the app is idle.` : r.note);
    } catch (e) {
      setNote((e as Error).message);
    }
  }

  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button className="rounded-md border border-line px-3 py-1.5 text-sm" onClick={() => readNow()}>Read every source now</button>
        {note && <span className="text-xs text-muted">{note}</span>}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {data.connectors.map((c) => <ConnectorCard key={c.name} c={c} onRead={() => readNow(c.name)} />)}
      </div>
      <p className="text-xs text-muted">
        A source whose read fails is shown here and backs off (its interval doubles with each failure in a row, up to
        {" "}{data.backoffCap}); it does not stop the others. Credentials stay in the environment and are never shown.
      </p>
    </div>
  );
}

function ConnectorCard({ c, onRead }: { c: Connector; onRead: () => void }) {
  const failing = c.failures > 0;
  return (
    <article className={`rounded-xl border bg-surface p-4 text-sm ${failing ? "border-risk-high" : "border-line"}`}>
      <header className="mb-2 flex items-baseline gap-2">
        <h3 className="font-semibold">{c.name}</h3>
        <span className="rounded bg-subtle px-1.5 py-0.5 text-xs">{c.mode}</span>
        <span className={`ml-auto text-xs ${failing ? "text-risk-high" : "text-risk-low"}`}>
          {failing ? `failing (${c.failures} in a row)` : c.lastRead ? "ok" : "not read yet"}
        </span>
      </header>
      <p className="mb-2 text-xs text-muted">{c.source}</p>
      <dl className="grid grid-cols-[7rem_1fr] gap-x-2 gap-y-1 text-xs">
        <dt className="text-muted">Interval</dt><dd>every {c.every}</dd>
        <dt className="text-muted">Cursor</dt><dd>{c.cursor}</dd>
        <dt className="text-muted">Last success</dt>
        <dd>{c.lastSuccess ? <>{when(c.lastSuccess.at)}: {c.lastSuccess.items} items, {c.lastSuccess.events} changes{c.lastSuccess.note && <span className="text-muted"> · {c.lastSuccess.note}</span>}</> : "none yet"}</dd>
        <dt className="text-muted">Last error</dt>
        <dd className={c.lastError ? "text-risk-high" : ""}>{c.lastError ? <>{when(c.lastError.at)}: {c.lastError.message}</> : "none"}</dd>
        <dt className="text-muted">Next read</dt><dd>{!c.nextRead ? "on the next detection run" : c.due
          ? `due since ${when(c.nextRead)}: runs when the app is next idle`
          : `${when(c.nextRead)} (${relative(c.nextRead)})`}</dd>
      </dl>
      <button className="mt-3 rounded-md border border-line px-2 py-1 text-xs" onClick={onRead}>Read now</button>
    </article>
  );
}
