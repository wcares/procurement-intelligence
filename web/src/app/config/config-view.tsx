"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { ConfigSetting } from "@/lib/api/types";

type Draft = Record<string, string>;

const show = (v: string | number) => (v === "" ? "(not set)" : String(v));

export function ConfigView() {
  const [settings, setSettings] = useState<ConfigSetting[] | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.config().then((r) => setSettings(r.settings)).catch((e: Error) => setStatus(e.message));
  }, []);

  const groups = useMemo(() => {
    const by = new Map<string, ConfigSetting[]>();
    for (const s of settings ?? []) by.set(s.group, [...(by.get(s.group) ?? []), s]);
    return [...by.entries()];
  }, [settings]);

  const changed = Object.keys(draft).filter((k) => draft[k] !== String(settings?.find((s) => s.key === k)?.value ?? ""));

  async function apply(save: boolean) {
    setBusy(true);
    setStatus(null);
    try {
      const values = Object.fromEntries(changed.map((k) => [k, draft[k]]));
      const r = await api.updateConfig({ values, save });
      if ("errors" in r) {
        setErrors(r.errors);
        setStatus("Nothing was changed: fix the highlighted settings.");
      } else {
        setSettings(r.settings);
        setDraft({});
        setErrors({});
        setStatus(save ? "Applied and saved." : "Applied. Not saved: the backend returns to the saved values after a restart.");
      }
    } catch (e) {
      setStatus((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!settings) return <p className="mx-auto max-w-3xl text-sm text-muted">{status ?? "Loading settings…"}</p>;

  const input = "w-full rounded-md border bg-background px-2 py-1.5 font-mono text-sm outline-none focus:border-accent";
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      {groups.map(([group, items]) => (
        <section key={group}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">{group}</h2>
          <div className="divide-y divide-line rounded-xl border border-line bg-surface">
            {items.map((s) => {
              const value = draft[s.key] ?? String(s.value);
              const err = errors[s.key];
              return (
                <div key={s.key} className="grid gap-2 p-4 sm:grid-cols-[1fr_16rem] sm:items-start">
                  <div>
                    <label htmlFor={`cfg-${s.key}`} className="text-sm font-medium">
                      {s.label}
                    </label>
                    {!s.editable && <span className="ml-2 rounded bg-subtle px-1.5 py-0.5 text-xs text-muted">read-only</span>}
                    <p className="mt-1 text-xs text-muted">{s.note}</p>
                    <p className="mt-1 text-xs text-muted">
                      At startup: <span className="font-mono">{show(s.default)}</span>
                      {s.min !== null && s.max !== null && <> · range {s.min}–{s.max}</>}
                    </p>
                  </div>
                  <div>
                    <input
                      id={`cfg-${s.key}`}
                      className={`${input} ${err ? "border-risk-high" : "border-line"} disabled:opacity-60`}
                      value={value}
                      disabled={!s.editable || busy}
                      inputMode={s.type === "int" || s.type === "float" ? "decimal" : undefined}
                      placeholder="(not set)"
                      onChange={(e) => setDraft((d) => ({ ...d, [s.key]: e.target.value }))}
                    />
                    {err && <p className="mt-1 text-xs text-risk-high">{err}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ))}
      <div className="sticky bottom-4 flex flex-wrap items-center gap-3 rounded-xl border border-line bg-surface p-3 shadow-sm">
        <button
          className="rounded-md bg-accent px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:text-black"
          disabled={busy || changed.length === 0}
          onClick={() => apply(false)}
        >
          Apply {changed.length > 0 && `(${changed.length})`}
        </button>
        <button
          className="rounded-md border border-line px-4 py-1.5 text-sm disabled:opacity-50"
          disabled={busy || changed.length === 0}
          onClick={() => apply(true)}
        >
          Apply and save
        </button>
        {changed.length > 0 && (
          <button className="text-sm text-muted hover:underline" disabled={busy} onClick={() => (setDraft({}), setErrors({}))}>
            Discard
          </button>
        )}
        {status && <span className="text-sm text-muted">{status}</span>}
      </div>
    </div>
  );
}
