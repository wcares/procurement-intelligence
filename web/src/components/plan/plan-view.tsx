"use client";

import { useState } from "react";
import { ManualPlan } from "./manual-plan";
import { PlanChat } from "./plan-chat";
import { PlanResults } from "./plan-results";
import { usePlan, type PlanState } from "./use-plan";

type Tab = "chat" | "manual";
const money = (v?: number) => (v ? (v >= 1e6 ? `US$${(v / 1e6).toFixed(1)}M` : `US$${Math.round(v / 1e3)}k`) : "");

/** Plan a project, two ways onto one plan: talk to the assistant (default) or fill the form. */
export function PlanView() {
  const s = usePlan();
  const [tab, setTab] = useState<Tab>("chat");
  if (!s.ready) return <p className="text-sm text-ink-muted">Loading…</p>;
  const tabBtn = (t: Tab, label: string) => (
    <button type="button" onClick={() => setTab(t)} aria-pressed={tab === t}
      className={`rounded-md px-3 py-1.5 text-sm ${tab === t ? "bg-brand text-white dark:text-black" : "border border-line text-ink-muted hover:bg-subtle"}`}>{label}</button>
  );
  return (
    <div className="space-y-4">
      <div className="flex gap-2">{tabBtn("chat", "Chat")}{tabBtn("manual", "Manual")}</div>
      {tab === "manual" ? <ManualPlan s={s} /> : (
        <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
          <PlanChat s={s} />
          <PlanPanel s={s} />
        </div>
      )}
    </div>
  );
}

/** The plan beside the chat: what has been understood so far, and the forecast once it has run. */
function PlanPanel({ s }: { s: PlanState }) {
  const country = s.opts?.countries.find((c) => c.code === s.countryCode)?.name;
  const named = s.packages.filter((p) => p.name || p.estimatedValueUsd);
  return (
    <section className="min-w-0 space-y-4">
      <div className="rounded-xl border border-line bg-surface p-4">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <h2 className="font-semibold">Your plan</h2>
          {named.length > 0 && <button className="text-xs underline" onClick={s.clear}>Clear plan</button>}
        </div>
        {named.length === 0 ? (
          <p className="text-sm text-ink-muted">Nothing yet. The plan builds up here as you talk.</p>
        ) : (
          <div className="space-y-2 text-sm">
            <p className="text-xs text-ink-muted">{country ?? "Country not set"} · start {s.projectStart}{s.deadline ? ` · deadline ${s.deadline}` : ""}</p>
            <ul className="divide-y divide-line">
              {named.map((p) => (
                <li key={p.id} className="py-1.5">
                  <span className="font-medium">{p.name || "Unnamed package"}</span>
                  <span className="text-xs text-ink-muted"> · {p.procGroup} · {p.methodCode}{p.estimatedValueUsd ? ` · ${money(p.estimatedValueUsd)}` : ""}
                    {p.after ? ` · after ${s.packages.find((x) => x.id === p.after)?.name ?? "another package"}` : ""}</span>
                  {s.errors[p.id] && <span className="block text-xs text-risk-high">{s.errors[p.id]}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {s.running && <p className="text-sm text-ink-muted">{s.progress || "Forecasting…"}</p>}
      {s.ran && !s.running && (
        <>
          <PlanResults packages={s.packages} plan={s.plan} forecasts={s.forecasts} projectStart={s.projectStart} deadline={s.deadline} />
          <p className="text-xs text-ink-muted">
            Each forecast comes from comparable past packages; the project dates combine them in the order set. The system has not
            learned how packages depend on each other, so treat the project dates as a planning aid. The Procurement Regulations
            decide which methods are allowed. Use the Manual tab to edit any detail.
          </p>
        </>
      )}
    </section>
  );
}
