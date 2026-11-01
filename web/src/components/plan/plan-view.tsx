"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { AssessView } from "@/app/assess/assess-view";
import { PlanChat } from "./plan-chat";
import { usePlan } from "./use-plan";

type Tab = "chat" | "assess";
const TABS = ["chat", "assess"];

/** The planning workspace: plan a project in the chat (each forecast gives a link to the plan's own page, where it is
 * edited and exported; questions about past projects are asked in the same chat), or assess a package. */
export function PlanView() {
  const s = usePlan();
  const [tab, setTab] = useState<Tab>(((t) => (TABS.includes(t ?? "") ? t : "chat") as Tab)(useSearchParams().get("tab")));   // /assess and /ask redirect here
  if (!s.ready) return <p className="text-sm text-ink-muted">Loading…</p>;
  return (
    // fills the space between the header and the footer; the negative margins cancel the page padding
    <div className="-mx-4 -my-8 flex h-[calc(100dvh-116px)] min-h-[560px] flex-col lg:-mx-8 print:h-auto print:min-h-0">
      <div className="flex h-11 items-stretch gap-6 border-b border-line px-4 text-sm lg:px-8 print:hidden" role="tablist" aria-label="Planning workspace">
        {(["chat", "assess"] as const).map((t) => (
          <button key={t} type="button" role="tab" onClick={() => setTab(t)} aria-selected={tab === t}
            className={`border-b-2 transition-colors ${tab === t ? "border-brand-2 font-semibold text-brand-strong" : "border-transparent text-ink-muted hover:text-foreground"}`}>
            {t === "chat" ? "Chat" : "Assess a package"}
          </button>
        ))}
      </div>
      {tab === "assess" ? (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 lg:px-8 print:overflow-visible">
          <p className="mb-5 max-w-2xl text-sm text-ink-muted">See how comparable World Bank–financed packages actually went, and what past evaluations say went wrong, with every lesson quoted from its source.</p>
          <AssessView />
        </div>
      ) : (
        <div className="flex min-h-0 w-full flex-1"><PlanChat s={s} /></div>
      )}
    </div>
  );
}
