"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { Options } from "@/lib/api/types";
import { forecastOf, schedule, type Forecast, type PlanPackage } from "@/lib/plan";
import { PackageCard } from "./package-card";
import { PlanResults } from "./plan-results";

const KEY = "procintel-plan";
const field = "w-full rounded-md border border-line bg-surface px-2 py-1.5 text-sm outline-none focus:border-brand";
const today = () => new Date().toISOString().slice(0, 10);
const newPackage = (): PlanPackage => ({ id: Math.random().toString(36).slice(2, 9), name: "", procGroup: "CW", methodCode: "RFB" });

interface Saved { countryCode: string; projectStart: string; deadline?: string; packages: PlanPackage[] }

/** Plan a project: several packages, a forecast for each, and the dates and bottleneck that follow. */
export function PlanView() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [countryCode, setCountryCode] = useState("KE");
  const [projectStart, setProjectStart] = useState("");  // set in the effect: a date is not allowed during prerender
  const [deadline, setDeadline] = useState<string | undefined>();
  const [packages, setPackages] = useState<PlanPackage[]>([]);
  const [ready, setReady] = useState(false);
  const [forecasts, setForecasts] = useState<Record<string, Forecast | undefined>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [ran, setRan] = useState(false);

  useEffect(() => {
    api.options().then(setOpts).catch(() => null);
    let saved: Saved | null = null;
    try { saved = JSON.parse(localStorage.getItem(KEY) ?? "null"); } catch { /* no saved plan, or storage blocked */ }
    if (saved?.packages?.length) {
      setCountryCode(saved.countryCode); setProjectStart(saved.projectStart || today()); setDeadline(saved.deadline); setPackages(saved.packages);
    } else {
      setProjectStart(today()); setPackages([newPackage()]);
    }
    setReady(true);
  }, []);
  useEffect(() => {
    if (!ready) return;
    try { localStorage.setItem(KEY, JSON.stringify({ countryCode, projectStart, deadline, packages } satisfies Saved)); } catch { /* storage blocked */ }
  }, [ready, countryCode, projectStart, deadline, packages]);

  const regions = useMemo(() => {
    const by = new Map<string, Options["countries"]>();
    for (const c of opts?.countries ?? []) by.set(c.region, [...(by.get(c.region) ?? []), c]);
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [opts]);

  const plan = useMemo(() => schedule(packages, forecasts, projectStart), [packages, forecasts, projectStart]);

  function update(p: PlanPackage) {
    setPackages((ps) => ps.map((x) => (x.id === p.id ? p : x)));
    setForecasts((f) => ({ ...f, [p.id]: undefined }));  // a changed package no longer matches its forecast
  }
  function remove(id: string) {
    setPackages((ps) => ps.filter((x) => x.id !== id).map((x) => (x.after === id ? { ...x, after: undefined } : x)));
  }

  async function run() {
    setRunning(true); setRan(true); setErrors({}); setForecasts({});
    for (const p of packages) {
      try {
        const r = await api.assess({
          countryCode, procGroup: p.procGroup, methodCode: p.methodCode, sector: p.sector,
          estimatedValueUsd: p.estimatedValueUsd, description: p.description,
        });
        const f = forecastOf(r);
        setForecasts((all) => ({ ...all, [p.id]: f ?? undefined }));
        if (!f) setErrors((e) => ({ ...e, [p.id]: "Too few comparable packages for a forecast." }));
      } catch (e) {
        setErrors((all) => ({ ...all, [p.id]: (e as Error).message }));
      }
    }
    setRunning(false);
  }

  if (!ready) return <p className="text-sm text-ink-muted">Loading…</p>;
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_1fr]">
      <div className="space-y-4">
        <div className="grid gap-3 rounded-xl border border-line bg-surface p-4 sm:grid-cols-3">
          <label className="text-xs sm:col-span-3">Country
            <select className={field} value={countryCode} onChange={(e) => { setCountryCode(e.target.value); setForecasts({}); }} disabled={!opts}>
              {regions.map(([region, cs]) => (
                <optgroup key={region} label={region}>{cs.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</optgroup>
              ))}
            </select>
          </label>
          <label className="text-xs sm:col-span-1">Project start
            <input type="date" className={field} value={projectStart} onChange={(e) => setProjectStart(e.target.value || today())} />
          </label>
          <label className="text-xs sm:col-span-2">Deadline for all awards (optional)
            <input type="date" className={field} value={deadline ?? ""} onChange={(e) => setDeadline(e.target.value || undefined)} />
          </label>
        </div>
        {packages.map((p) => (
          <PackageCard key={p.id} pkg={p} others={packages.filter((o) => o.id !== p.id)} opts={opts} countryCode={countryCode}
            forecast={forecasts[p.id]} status={errors[p.id]} onChange={update} onRemove={() => remove(p.id)} />
        ))}
        <div className="flex flex-wrap gap-3">
          <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => setPackages((ps) => [...ps, newPackage()])}>Add a package</button>
          <button type="button" disabled={!opts || running || packages.length === 0}
            className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-black" onClick={run}>
            {running ? "Forecasting…" : "Forecast the project"}
          </button>
        </div>
        <p className="text-xs text-ink-muted">Your plan is kept in this browser only.</p>
      </div>

      <section className="min-w-0 space-y-4">
        {!ran ? (
          <div className="rounded-xl border border-dashed border-line p-10 text-center text-ink-muted">
            Add the packages of the project, then forecast it to see when each is likely to be awarded, which one holds the
            project back, and whether a deadline is realistic.
          </div>
        ) : (
          <>
            <PlanResults packages={packages} plan={plan} forecasts={forecasts} projectStart={projectStart} deadline={deadline} />
            <p className="text-xs text-ink-muted">
              Each forecast comes from comparable past packages; the project dates combine them in the order you set.
              The system has not learned how packages depend on each other, so treat the project dates as a planning
              aid, not a prediction of the whole project. The Procurement Regulations decide which methods are allowed.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
