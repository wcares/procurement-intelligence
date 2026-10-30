"use client";

import { useState } from "react";
import type { AskResponse } from "@/lib/api/types";
import { Caveats, CitationCard } from "@/components/evidence";
import { FeedbackBar, FlagCitation } from "@/components/feedback";
import { AnswerMap } from "./answer-map";

/** An answer from the reports: the sentences with their citation chips and the quoted sources below. When nothing answered
 * the question directly it shows the fallback reply (what was searched and what is close) under a plain label. */
export function Answer({ turnId, r: full, question }: { turnId: number; r: AskResponse; question: string }) {
  const partial = full.unsupported;   // nothing answered it directly: the reply says what was tried and what is close
  const r = partial && full.fallback ? { ...full, ...full.fallback } : full;
  const [asMap, setAsMap] = useState(false);
  const toSource = (i: number) => {
    const el = document.getElementById(`t${turnId}-c${i}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.classList.add("ring-2", "ring-brand", "rounded-xl");
    setTimeout(() => el?.classList.remove("ring-2", "ring-brand"), 1500);
  };
  return (
    <div className="space-y-3">
      {!partial && <button className="text-xs text-ink-muted underline" onClick={() => setAsMap(!asMap)}>{asMap ? "Show as text" : "Show as map"}</button>}
      {asMap && !partial && <AnswerMap r={r} question={question} onSource={toSource} />}
      {partial && <span className="inline-block rounded-full bg-risk-medium-soft px-2.5 py-0.5 text-xs font-medium text-risk-medium">No direct answer in the reports</span>}
      <div className="text-sm leading-relaxed">
        {r.answer.map((s, i) => (
          <span key={i}>
            {s.text}{" "}
            {s.citations.map((c) => (
              <a key={c} href={`#t${turnId}-c${c}`} className="mx-px inline-grid h-[18px] min-w-[18px] place-items-center rounded-md bg-brand-soft px-1 align-[1px] font-mono text-[11px] font-medium text-brand hover:bg-brand hover:text-[#f1f4ff]">
                [{c + 1}]
              </a>
            ))}{" "}
          </span>
        ))}
      </div>
      <div className="space-y-2">
        {r.citations.map((c, i) => (
          <div key={c.id} id={`t${turnId}-c${i}`} className="scroll-mt-20">
            <CitationCard
              c={c}
              index={i}
              highlight={r.answer.find((s) => s.citations.includes(i))?.text}
              action={<FlagCitation responseId={r.meta.responseId} citationId={c.id} />}
            />
          </div>
        ))}
      </div>
      {partial ? <details className="text-xs text-ink-muted"><summary className="cursor-pointer">How this was searched</summary><div className="mt-2"><Caveats meta={r.meta} /></div></details> : <Caveats meta={r.meta} />}
      <FeedbackBar responseId={r.meta.responseId} subject="answer" />
    </div>
  );
}
