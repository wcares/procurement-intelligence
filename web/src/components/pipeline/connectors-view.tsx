"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Connector, ConnectorSettings, ConnectorsResponse } from "@/lib/api/types";
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
  if (!data) return <p className="text-sm text-ink-muted">Loading…</p>;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button className="rounded-md border border-line px-3 py-1.5 text-sm" onClick={() => readNow()}>Read every source now</button>
        {note && <span className="text-xs text-ink-muted">{note}</span>}
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {data.connectors.map((c) => <ConnectorCard key={c.name} c={c} onRead={() => readNow(c.name)} onSaved={setData} />)}
      </div>
      <p className="text-xs text-ink-muted">
        A source whose read fails is shown here and backs off (its interval doubles with each failure in a row, up to
        {" "}{data.backoffCap}); it does not stop the others. Credentials stay in the environment and are never shown.
      </p>
    </div>
  );
}

function ConnectorCard({ c, onRead, onSaved }: { c: Connector; onRead: () => void; onSaved: (d: ConnectorsResponse) => void }) {
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
      <p className="mb-2 text-xs text-ink-muted">{c.source}</p>
      <dl className="grid grid-cols-[7rem_1fr] gap-x-2 gap-y-1 text-xs">
        <dt className="text-ink-muted">Interval</dt><dd>every {c.every}</dd>
        <dt className="text-ink-muted">Cursor</dt><dd>{c.cursor}</dd>
        <dt className="text-ink-muted">Last success</dt>
        <dd>{c.lastSuccess ? <>{when(c.lastSuccess.at)}: {c.lastSuccess.items} items, {c.lastSuccess.events} changes{c.lastSuccess.note && <span className="text-ink-muted"> · {c.lastSuccess.note}</span>}</> : "none yet"}</dd>
        <dt className="text-ink-muted">Last error</dt>
        <dd className={c.lastError ? "text-risk-high" : ""}>{c.lastError ? <>{when(c.lastError.at)}: {c.lastError.message}</> : "none"}</dd>
        <dt className="text-ink-muted">Next read</dt><dd>{!c.nextRead ? "on the next detection run" : c.due
          ? `due since ${when(c.nextRead)}: runs when the app is next idle`
          : `${when(c.nextRead)} (${relative(c.nextRead)})`}</dd>
      </dl>
      {c.settings.mode === "push" && (
        <p className="mt-2 text-xs">
          Push: the source posts to <span className="font-mono">{c.push.path}</span>, signed with{" "}
          <span className="font-mono">{c.push.secretVar}</span>{" "}
          {c.push.secretSet ? <span className="text-risk-low">(secret set)</span> : <span className="text-risk-high">(secret not set: pushes are refused)</span>}.
          Still read once a day to catch lost pushes.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button className="rounded-md border border-line px-2 py-1 text-xs" onClick={onRead}>Read now</button>
        <SettingsEditor c={c} onSaved={onSaved} />
      </div>
    </article>
  );
}


/** Mode, interval and on/off for one source, saved to the data folder (procintel.pipeline.connector_config). */
function SettingsEditor({ c, onSaved }: { c: Connector; onSaved: (d: ConnectorsResponse) => void }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<ConnectorSettings>(c.settings);
  const [error, setError] = useState<string | null>(null);
  async function save(change: Partial<ConnectorSettings>) {
    const r = await api.saveConnector(c.name, change).catch((e) => ({ error: (e as Error).message }));
    if ("error" in r) return setError(r.error);
    setError(null);
    setOpen(false);
    onSaved(r);
  }
  if (!open) {
    return (
      <button className="text-xs underline" onClick={() => (setDraft(c.settings), setOpen(true))}>
        settings{c.customised ? " (changed)" : ""}{c.settings.enabled ? "" : " · off"}
      </button>
    );
  }
  return (
    <div className="flex w-full flex-wrap items-center gap-2 rounded-md bg-subtle p-2 text-xs">
      <label className="flex items-center gap-1">Mode
        <select className="rounded border border-line bg-surface px-1 py-0.5" value={draft.mode}
          onChange={(e) => setDraft({ ...draft, mode: e.target.value as ConnectorSettings["mode"] })}>
          <option value="poll">poll</option>
          <option value="push">push (webhook)</option>
        </select>
      </label>
      {draft.mode === "poll" && (
        <label className="flex items-center gap-1">every
          <input type="number" min={0.25} step={0.25} className="w-20 rounded border border-line bg-surface px-1 py-0.5"
            value={draft.everyHours} onChange={(e) => setDraft({ ...draft, everyHours: Number(e.target.value) })} /> hours
        </label>
      )}
      <label className="flex items-center gap-1">
        <input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} /> on
      </label>
      <button className="rounded-md border border-line px-2 py-0.5" onClick={() => save(draft)}>Save</button>
      {c.customised && <button className="underline" onClick={() => save(c.defaults)}>reset to defaults</button>}
      <button className="text-ink-muted underline" onClick={() => setOpen(false)}>cancel</button>
      {error && <span className="text-risk-high">{error}</span>}
    </div>
  );
}
