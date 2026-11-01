"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { ChatPlan, Options } from "@/lib/api/types";
import { forecastOf, resultsText, schedule, todayLocal, type Forecast, type PlanPackage } from "@/lib/plan";

const KEY = "procintel-plan";
const today = todayLocal;
export const newPackage = (): PlanPackage => ({ id: Math.random().toString(36).slice(2, 9), name: "", procGroup: "CW", methodCode: "RFB" });

export interface Saved { countryCode: string; projectStart: string; deadline?: string; packages: PlanPackage[] }
/** A plan as a link keeps it: the plan with the forecasts it was shown with. */
export interface PlanSnapshot extends Saved { forecasts?: Record<string, Forecast | undefined> }

/** The plan and its forecasts. The chat keeps its plan in this browser (local storage); the plan page behind a link
 * starts from that link's snapshot instead and keeps nothing locally (save writes it back to the link). */
export function usePlan(initial?: PlanSnapshot) {
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
    let saved: Saved | null = initial ?? null;
    if (!initial) {
      try { saved = JSON.parse(localStorage.getItem(KEY) ?? "null"); } catch { /* no saved plan, or storage blocked */ }
    } else if (initial.forecasts) {
      setForecasts(initial.forecasts); setRan(true);
    }
    if (saved?.packages?.length) {
      setCountryCode(saved.countryCode); setProjectStart(saved.projectStart || today()); setDeadline(saved.deadline); setPackages(saved.packages);
    } else {
      setProjectStart(today()); setPackages([newPackage()]);
    }
    setReady(true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- read once, on mount
  useEffect(() => {
    if (!ready || initial) return;
    try { localStorage.setItem(KEY, JSON.stringify({ countryCode, projectStart, deadline, packages } satisfies Saved)); } catch { /* storage blocked */ }
  }, [ready, initial, countryCode, projectStart, deadline, packages]);

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
          withPrecedents: false,  // the plan shows dates and risks, not passages: skipping them saves a model call a package
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

  const asChatPlan = useCallback((): ChatPlan => ({ countryCode: countryCode || null, projectStart: projectStart || null, deadline: deadline ?? null, packages: packages.filter((p) => p.name.trim() || p.estimatedValueUsd || p.description?.trim()) }), [countryCode, projectStart, deadline, packages]);
  const results = useMemo(() => (ran && !running ? resultsText(packages, forecasts, plan) : ""), [ran, running, packages, forecasts, plan]);
  const clear = useCallback(() => { setPackages([]); setForecasts({}); setErrors({}); setRan(false); setDeadline(undefined); }, []);

  return { opts, ready, countryCode, setCountryCode, projectStart, setProjectStart, deadline, setDeadline, packages, setPackages,
    forecasts, setForecasts, errors, running, progress, ran, plan, update, remove, run, adopt, asChatPlan, results, clear };
}

export type PlanState = ReturnType<typeof usePlan>;

/** Hand a plan (from its page) to the chat in this browser, so the conversation continues from it. */
export function keepForChat(p: Saved) {
  try { localStorage.setItem(KEY, JSON.stringify({ countryCode: p.countryCode, projectStart: p.projectStart, deadline: p.deadline, packages: p.packages })); } catch { /* storage blocked */ }
}
