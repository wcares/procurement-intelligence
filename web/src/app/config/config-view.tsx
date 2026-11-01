"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { CompareResponse, ConfigProfile, ConfigSetting, RetrievalMetrics } from "@/lib/api/types";
import { FeedbackReview } from "@/components/evaluation/feedback-review";
import { Jobs } from "./jobs-panel";
import { JobsList } from "./jobs-list";
import Link from "next/link";
import { Prompts } from "./prompts-panel";
import { Users } from "./users-panel";

type Draft = Record<string, string>;

const show = (v: string | number) => (v === "" ? "(not set)" : String(v));

// Hidden 2026-10-28, not removed: the prompt texts, saved profiles, job queue and pages that Evaluation and Pipeline already
// have are for engineers, not for the people this is shown to. Set to true to bring them back.
const SHOW_ADVANCED = false;

export function ConfigView() {
  const [settings, setSettings] = useState<ConfigSetting[] | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [section, setSection] = useState("accounts");

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

  if (!settings) return <p className="text-sm text-ink-muted">{status ?? "Loading settings…"}</p>;

  // Sections down the left, as in Vercel's settings: accounts first, then each group of backend settings.
  const sections = [{ id: "accounts", label: "Accounts" }, ...groups.map(([g]) => ({ id: slug(g), label: g })), { id: "jobs", label: "Background jobs" },
    ...(SHOW_ADVANCED ? [{ id: "advanced", label: "Advanced" }] : [])];
  const current = sections.some((x) => x.id === section) ? section : sections[0].id;
  const input = "w-full max-w-md rounded-md border bg-surface px-3 py-2 font-mono text-sm outline-none focus:border-brand-2";

  async function saveOne(key: string) {
    setBusy(true);
    setStatus(null);
    try {
      const r = await api.updateConfig({ values: { [key]: draft[key] }, save: true });
      if ("errors" in r) setErrors(r.errors);
      else {
        setSettings(r.settings);
        setDraft((d) => omit(d, key));
        setErrors((d) => omit(d, key));
        setStatus("Saved.");
      }
    } catch (e) {
      setStatus((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-10 md:grid-cols-[200px_minmax(0,1fr)]">
      <nav className="md:sticky md:top-24 md:self-start" aria-label="Settings sections">
        <ul className="flex gap-1 overflow-x-auto md:flex-col">
          {sections.map((x) => (
            <li key={x.id}>
              <button type="button" onClick={() => setSection(x.id)} aria-current={current === x.id ? "page" : undefined}
                className={`w-full whitespace-nowrap rounded-md px-3 py-2 text-left text-sm transition-colors ${current === x.id ? "bg-subtle font-semibold text-foreground" : "text-ink-muted hover:text-foreground"}`}>
                {x.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="min-w-0 space-y-6">
        {status && <p className="text-sm text-ink-muted">{status}</p>}
        {current === "accounts" && <Users />}
        {current === "jobs" && <JobsList />}
        {current === "advanced" && (
          <div className="space-y-8">
            <Jobs />
            <p className="text-sm">Sources, change events and rules have their own pages: <Link className="underline" href="/pipeline">connectors</Link>,{" "}
              <Link className="underline" href="/pipeline/events">event log</Link>, <Link className="underline" href="/pipeline/rules">rules</Link>.</p>
            <FeedbackReview />
            <Prompts />
            <Profiles disabled={busy} onApplied={(x) => (setSettings(x), setDraft({}), setErrors({}), setComparison(null))} onStatus={setStatus} />
          </div>
        )}
        {groups.filter(([g]) => slug(g) === current).map(([group, items]) => {
          const pending = items.filter((x) => changed.includes(x.key));
          return (
            <div key={group} className="space-y-6">
              <h2 className="text-xl font-semibold">{group}</h2>
              {items.map((x) => {
                const value = draft[x.key] ?? String(x.value);
                const err = errors[x.key];
                const dirty = changed.includes(x.key);
                return (
                  <section key={x.key} className="overflow-hidden rounded-lg border border-line bg-surface">
                    <div className="space-y-3 p-5">
                      <div>
                        <label htmlFor={`cfg-${x.key}`} className="font-semibold">{x.label}</label>
                        <p className="mt-1 text-sm text-ink-muted">{x.note}</p>
                      </div>
                      <input id={`cfg-${x.key}`} className={`${input} ${err ? "border-risk-high" : "border-line"} disabled:opacity-60`}
                        value={value} disabled={!x.editable || busy} placeholder="(not set)"
                        inputMode={x.type === "int" || x.type === "float" ? "decimal" : undefined}
                        onChange={(e) => setDraft((d) => ({ ...d, [x.key]: e.target.value }))} />
                      {err && <p className="text-sm text-risk-high">{err}</p>}
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-subtle px-5 py-3 text-xs text-ink-muted">
                      <span>
                        {x.editable ? <>At startup: <span className="font-mono">{show(x.default)}</span></> : "Set in the environment; read-only here."}
                        {x.min !== null && x.max !== null && <> · range {x.min}–{x.max}</>}
                      </span>
                      {x.editable && (
                        <span className="flex gap-2">
                          {dirty && <button type="button" className="rounded-md px-2 py-1 hover:text-foreground" onClick={() => setDraft((d) => omit(d, x.key))}>Cancel</button>}
                          <button type="button" disabled={!dirty || busy} onClick={() => void saveOne(x.key)}
                            className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium transition-opacity disabled:opacity-40">Save</button>
                        </span>
                      )}
                    </div>
                  </section>
                );
              })}
              {pending.length > 0 && (
                <section className="space-y-3 rounded-lg border border-line p-5">
                  <div>
                    <p className="font-semibold">Check before saving</p>
                    <p className="mt-1 text-sm text-ink-muted">Measure search quality on the evaluation questions with the {pending.length} unsaved change{pending.length > 1 ? "s" : ""}, or try them until the next restart without saving.</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50" disabled={busy} onClick={check}>Check search quality</button>
                    <button type="button" className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50" disabled={busy} onClick={() => apply(false)}>Try without saving</button>
                  </div>
                  {comparison && <Comparison c={comparison} />}
                </section>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const omit = <T,>(o: Record<string, T>, k: string): Record<string, T> => Object.fromEntries(Object.entries(o).filter(([x]) => x !== k));
const slug = (g: string) => g.toLowerCase().replace(/[^a-z0-9]+/g, "-");

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
        <thead className="text-left text-xs text-ink-muted">
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
      <p className="mt-1 text-xs text-ink-muted">Search only, against the judged relevance labels. Answers are not re-run (the full evaluation takes about 90 minutes).</p>
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
      <h2 className="mb-3 text-lg font-semibold">Profiles</h2>
      <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
        <p className="text-xs text-ink-muted">A profile stores every editable setting as it is now, so a tested setup can be restored in one step.</p>
        {profiles.length === 0 ? (
          <p className="text-sm text-ink-muted">No saved profiles.</p>
        ) : (
          <ul className="divide-y divide-line">
            {profiles.map((p) => (
              <li key={p.name} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className="font-medium">{p.name}</span>
                <span className="text-xs text-ink-muted">
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
                    className="text-xs text-ink-muted hover:underline disabled:opacity-50"
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
            className="w-full rounded-md border border-line bg-background px-2 py-1.5 text-sm outline-none focus:border-brand"
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
