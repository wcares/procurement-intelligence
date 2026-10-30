"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { AssessView } from "@/app/assess/assess-view";
import { AskView } from "@/app/ask/ask-view";
import { ManualPlan } from "./manual-plan";
import { PlanChat } from "./plan-chat";
import { PlanResults } from "./plan-results";
import { usePlan, type PlanState } from "./use-plan";

type Tab = "chat" | "manual" | "assess" | "ask";
const TABS = ["chat", "manual", "assess", "ask"];
const money = (v?: number) => (v ? (v >= 1e6 ? `US$${(v / 1e6).toFixed(1)}M` : `US$${Math.round(v / 1e3)}k`) : "");

/** Plan a project, two ways onto one plan: talk to the assistant (default) or fill the form. */
export function PlanView() {
  const s = usePlan();
  const [tab, setTab] = useState<Tab>(((t) => (TABS.includes(t ?? "") ? t : "chat") as Tab)(useSearchParams().get("tab")));   // /assess and /ask redirect here
  const [pane, setPane] = useState<"chat" | "plan">("chat");   // narrow screens show one side at a time
  if (!s.ready) return <p className="text-sm text-ink-muted">Loading…</p>;
  const seg = (on: boolean) => `rounded-lg px-3.5 py-1.5 text-sm font-medium ${on ? "bg-brand" : "text-ink-muted hover:text-foreground"}`;
  const count = s.packages.filter((p) => p.name || p.estimatedValueUsd).length;
  return (
    // fills the space between the header and the footer; the negative margins cancel the page padding
    <div className="-mx-4 -my-8 flex h-[calc(100dvh-110px)] min-h-[560px] flex-col lg:-mx-8">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 lg:px-8">
        <h1 className="text-[15px] font-semibold tracking-tight">Plan a project</h1>
        <div className="inline-flex gap-0.5 rounded-[10px] bg-subtle p-[3px]" role="group" aria-label="Plan mode">
          <button type="button" onClick={() => setTab("chat")} aria-pressed={tab === "chat"} className={seg(tab === "chat")}>Chat</button>
          <button type="button" onClick={() => setTab("manual")} aria-pressed={tab === "manual"} className={seg(tab === "manual")}>Manual</button>
          <button type="button" onClick={() => setTab("assess")} aria-pressed={tab === "assess"} className={seg(tab === "assess")}>Assess a package</button>
          <button type="button" onClick={() => setTab("ask")} aria-pressed={tab === "ask"} className={seg(tab === "ask")}>Ask the evidence</button>
        </div>
        {tab === "chat" && (
          <div className="inline-flex gap-0.5 rounded-[10px] bg-subtle p-[3px] lg:hidden" role="group" aria-label="Pane">
            <button type="button" onClick={() => setPane("chat")} aria-pressed={pane === "chat"} className={seg(pane === "chat")}>Conversation</button>
            <button type="button" onClick={() => setPane("plan")} aria-pressed={pane === "plan"} className={seg(pane === "plan")}>Plan{count ? ` (${count})` : ""}</button>
          </div>
        )}
        <p className="hidden text-xs text-ink-muted xl:block">Each package is forecast from comparable past packages and laid out on one timeline. Ask about the plan, or about past projects, in the same chat.</p>
      </div>
      {tab === "manual" ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 lg:px-8"><ManualPlan s={s} /></div>
      ) : tab === "ask" ? (
        <div className="min-h-0 flex-1"><AskView embedded /></div>
      ) : tab === "assess" ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 lg:px-8">
          <p className="mb-5 max-w-2xl text-sm text-ink-muted">See how comparable World Bank–financed packages actually went, and what past evaluations say went wrong, with every lesson quoted from its source.</p>
          <AssessView />
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <div className={`min-h-0 min-w-0 flex-col ${pane === "chat" ? "flex" : "hidden lg:flex"}`}><PlanChat s={s} /></div>
          <div className={`min-h-0 min-w-0 ${pane === "plan" ? "block" : "hidden lg:block"}`}><PlanPanel s={s} /></div>
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
    <section className="h-full min-w-0 space-y-4 overflow-y-auto border-l border-line bg-surface px-5 py-5 lg:px-6">
      <div>
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <h2 className="text-base font-semibold tracking-tight">Your plan</h2>
          {named.length > 0 && <button className="text-xs underline" onClick={s.clear}>Clear plan</button>}
        </div>
        {named.length === 0 ? (
          <p className="text-sm text-ink-muted">Nothing yet. The plan builds up here as you talk.</p>
        ) : (
          <div className="space-y-2 text-sm">
            <p className="text-xs text-ink-muted">{country ?? "Country not set"} · start {s.projectStart}{s.deadline ? ` · deadline ${s.deadline}` : ""}</p>
            <ul className="divide-y divide-line rounded-xl border border-line bg-subtle px-3.5">
              {named.map((p) => (
                <li key={p.id} className="py-2">
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
