"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { CompareResponse, ConfigProfile, ConfigSetting, RetrievalMetrics } from "@/lib/api/types";

type Draft = Record<string, string>;

const show = (v: string | number) => (v === "" ? "(not set)" : String(v));

export function ConfigView() {
  const [settings, setSettings] = useState<ConfigSetting[] | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [comparison, setComparison] = useState<CompareResponse | null>(null);

  useEffect(() => {
    api.config().then((r) => setSettings(r.settings)).catch((e: Error) => setStatus(e.message));
  }, []);

  const groups = useMemo(() => {
    const by = new Map<string, ConfigSetting[]>();
    for (const s of settings ?? []) by.set(s.group, [...(by.get(s.group) ?? []), s]);
    return [...by.entries()];
  }, [settings]);

  const changed = Object.keys(draft).filter((k) => draft[k] !== String(settings?.find((s) => s.key === k)?.value ?? ""));

  async function check() {
    setBusy(true);
    setStatus("Measuring search quality with the current and the changed settings…");
    try {
      setComparison(await api.compare(Object.fromEntries(changed.map((k) => [k, draft[k]]))));
      setStatus(null);
    } catch (e) {
      setStatus((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

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
        setComparison(null);
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
      <Profiles
        disabled={busy}
        onApplied={(s) => (setSettings(s), setDraft({}), setErrors({}), setComparison(null))}
        onStatus={setStatus}
      />
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
        <button
          className="rounded-md border border-line px-4 py-1.5 text-sm disabled:opacity-50"
          disabled={busy || changed.length === 0}
          onClick={check}
          title="Search quality over the evaluation questions, before and after the change; nothing is applied"
        >
          Check search quality
        </button>
        {changed.length > 0 && (
          <button className="text-sm text-muted hover:underline" disabled={busy} onClick={() => (setDraft({}), setErrors({}))}>
            Discard
          </button>
        )}
        {status && <span className="text-sm text-muted">{status}</span>}
        {comparison && <Comparison c={comparison} />}
      </div>
    </div>
  );
}

const METRICS: [keyof RetrievalMetrics, string][] = [
  ["hybrid_p5", "Hybrid precision@5"],
  ["hybrid_r10", "Hybrid recall@10"],
  ["bm25_p5", "Keyword precision@5"],
  ["bm25_r10", "Keyword recall@10"],
];

function Comparison({ c }: { c: CompareResponse }) {
  return (
    <div className="w-full text-sm">
      <table className="w-full tabular-nums">
        <thead className="text-left text-xs text-muted">
          <tr>
            <th className="font-normal">Search quality ({c.before.questions} evaluation questions)</th>
            <th className="font-normal">now</th>
            <th className="font-normal">with the changes</th>
          </tr>
        </thead>
        <tbody>
          {METRICS.map(([k, label]) => {
            const d = c.after[k] - c.before[k];
            return (
              <tr key={k}>
                <td>{label}</td>
                <td>{c.before[k].toFixed(2)}</td>
                <td className={d > 0.005 ? "text-risk-low" : d < -0.005 ? "text-risk-high" : ""}>
                  {c.after[k].toFixed(2)} {Math.abs(d) > 0.005 && `(${d > 0 ? "+" : ""}${d.toFixed(2)})`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-1 text-xs text-muted">Search only, against the judged relevance labels. Answers are not re-run (the full evaluation takes about 90 minutes).</p>
    </div>
  );
}

function Profiles({
  disabled,
  onApplied,
  onStatus,
}: {
  disabled: boolean;
  onApplied: (s: ConfigSetting[]) => void;
  onStatus: (s: string | null) => void;
}) {
  const [profiles, setProfiles] = useState<ConfigProfile[]>([]);
  const [name, setName] = useState("");

  useEffect(() => {
    api.profiles().then((r) => setProfiles(r.profiles)).catch(() => setProfiles([]));
  }, []);

  async function run(f: () => Promise<void>) {
    onStatus(null);
    try {
      await f();
    } catch (e) {
      onStatus((e as Error).message);
    }
  }

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Profiles</h2>
      <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
        <p className="text-xs text-muted">A profile stores every editable setting as it is now, so a tested setup can be restored in one step.</p>
        {profiles.length === 0 ? (
          <p className="text-sm text-muted">No saved profiles.</p>
        ) : (
          <ul className="divide-y divide-line">
            {profiles.map((p) => (
              <li key={p.name} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className="font-medium">{p.name}</span>
                <span className="text-xs text-muted">
                  {Object.keys(p.differs).length === 0 ? "same as startup" : `${Object.keys(p.differs).length} changed: ${Object.keys(p.differs).join(", ")}`}
                </span>
                <span className="ml-auto flex gap-2">
                  <button
                    className="rounded-md border border-line px-2 py-0.5 text-xs disabled:opacity-50"
                    disabled={disabled}
                    onClick={() => run(async () => (onApplied((await api.applyProfile(p.name, false)).settings), onStatus(`Profile "${p.name}" applied (not saved).`)))}
                  >
                    Apply
                  </button>
                  <button
                    className="text-xs text-muted hover:underline disabled:opacity-50"
                    disabled={disabled}
                    onClick={() => run(async () => setProfiles((await api.deleteProfile(p.name)).profiles))}
                  >
                    Delete
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => (setProfiles((await api.saveProfile(name)).profiles), setName(""), onStatus(`Saved the current settings as "${name}".`)));
          }}
        >
          <input
            className="w-full rounded-md border border-line bg-background px-2 py-1.5 text-sm outline-none focus:border-accent"
            placeholder="Profile name, e.g. fast answers"
            maxLength={60}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50" disabled={disabled || !name.trim()}>
            Save current
          </button>
        </form>
      </div>
    </section>
  );
}
