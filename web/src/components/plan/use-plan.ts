"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { ChatPlan, Options } from "@/lib/api/types";
import { forecastOf, resultsText, schedule, type Forecast, type PlanPackage } from "@/lib/plan";

const KEY = "procintel-plan";
const today = () => new Date().toISOString().slice(0, 10);
export const newPackage = (): PlanPackage => ({ id: Math.random().toString(36).slice(2, 9), name: "", procGroup: "CW", methodCode: "RFB" });

interface Saved { countryCode: string; projectStart: string; deadline?: string; packages: PlanPackage[] }

/** The plan and its forecasts, shared by the chat and the manual form: both edit the same plan. */
export function usePlan() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [countryCode, setCountryCode] = useState("KE");
  const [projectStart, setProjectStart] = useState("");  // set in the effect: a date is not allowed during prerender
  const [deadline, setDeadline] = useState<string | undefined>();
  const [packages, setPackages] = useState<PlanPackage[]>([]);
  const [ready, setReady] = useState(false);
  const [forecasts, setForecasts] = useState<Record<string, Forecast | undefined>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
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

  const plan = useMemo(() => schedule(packages, forecasts, projectStart), [packages, forecasts, projectStart]);

  const update = useCallback((p: PlanPackage) => {
    setPackages((ps) => ps.map((x) => (x.id === p.id ? p : x)));
    setForecasts((f) => ({ ...f, [p.id]: undefined }));  // a changed package no longer matches its forecast
  }, []);
  const remove = useCallback((id: string) => {
    setPackages((ps) => ps.filter((x) => x.id !== id).map((x) => (x.after === id ? { ...x, after: undefined } : x)));
  }, []);

  /** Forecast the given packages (default: the plan's) with the existing assessment; resolves with the results. */
  const run = useCallback(async (pkgs: PlanPackage[] = packages, country: string = countryCode) => {
    setRunning(true); setRan(true); setErrors({}); setForecasts({});
    const out: Record<string, Forecast | undefined> = {};
    for (const [i, p] of pkgs.entries()) {
      setProgress(`Forecasting ${p.name || "package"} (${i + 1} of ${pkgs.length})…`);
      try {
        const r = await api.assess({
          countryCode: country, procGroup: p.procGroup, methodCode: p.methodCode, sector: p.sector,
          estimatedValueUsd: p.estimatedValueUsd, description: p.description,
        });
        const f = forecastOf(r);
        out[p.id] = f ?? undefined;
        setForecasts((all) => ({ ...all, [p.id]: f ?? undefined }));
        if (!f) setErrors((e) => ({ ...e, [p.id]: "Too few comparable packages for a forecast." }));
      } catch (e) {
        setErrors((all) => ({ ...all, [p.id]: (e as Error).message }));
      }
    }
    setProgress(""); setRunning(false);
    return out;
  }, [packages, countryCode]);

  /** Adopt a plan the chat proposed (already checked by the backend). */
  const adopt = useCallback((p: ChatPlan) => {
    if (p.countryCode) setCountryCode(p.countryCode);
    setProjectStart(p.projectStart || today());
    setDeadline(p.deadline ?? undefined);
    setPackages(p.packages);
    setForecasts({}); setRan(false);
  }, []);

  const asChatPlan = useCallback((): ChatPlan => ({ countryCode: countryCode || null, projectStart: projectStart || null, deadline: deadline ?? null, packages }), [countryCode, projectStart, deadline, packages]);
  const results = useMemo(() => (ran && !running ? resultsText(packages, forecasts, plan) : ""), [ran, running, packages, forecasts, plan]);
  const clear = useCallback(() => { setPackages([]); setForecasts({}); setErrors({}); setRan(false); setDeadline(undefined); }, []);

  return { opts, ready, countryCode, setCountryCode, projectStart, setProjectStart, deadline, setDeadline, packages, setPackages,
    forecasts, setForecasts, errors, running, progress, ran, plan, update, remove, run, adopt, asChatPlan, results, clear };
}

export type PlanState = ReturnType<typeof usePlan>;
