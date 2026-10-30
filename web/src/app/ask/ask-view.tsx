"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { AskResponse, Options, ProcGroup } from "@/lib/api/types";
import { Caveats, CitationCard } from "@/components/evidence";
import { FeedbackBar, FlagCitation } from "@/components/feedback";
import { AnswerMap } from "@/components/ask/answer-map";
import { LiveAnswer, emptyLive, fold, type Live } from "@/components/ask/live-answer";
import { InsightsPanel } from "@/components/insights/insights-panel";

type Turn = { id: number; question: string; response?: AskResponse; error?: string; live?: Live };

const EXAMPLES = [
  { tag: "Cancellations", q: "Why were procurement processes cancelled or contracts terminated?" },
  { tag: "Delays", q: "What caused delays in civil works contracts?" },
  { tag: "Capacity", q: "What lessons were learned about procurement capacity of implementing agencies?" },
];
// Hidden 2026-10-28, not removed: alerts, the award-time chart and recommendations above the question repeat Overview and
// Insights. Set to true to bring them back.
const SHOW_INSIGHTS = false;

export function AskView() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [countryCode, setCountryCode] = useState("");
  const [procGroup, setProcGroup] = useState<ProcGroup | "">("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.options().then(setOpts).catch(() => setOpts(null));
  }, []);
  useEffect(() => {
    // block body on purpose: the effect must return nothing, and scrollIntoView's return value is not a cleanup function
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  async function send(q: string) {
    const text = q.trim();
    if (!text || busy) return;
    const id = Date.now();
    setTurns((t) => [...t, { id, question: text, live: emptyLive }]);
    setQuestion("");
    setBusy(true);
    try {
      const response = await api.askStream({ question: text, countryCode: countryCode || undefined, procGroup: procGroup || undefined },
        (e) => setTurns((t) => t.map((x) => (x.id === id && x.live ? { ...x, live: fold(x.live, e) } : x))));
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, response, live: undefined } : x)));
    } catch (e) {
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: (e as Error).message, live: undefined } : x)));
    } finally {
      setBusy(false);
    }
  }

  const select = "rounded-lg border border-line bg-subtle px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-brand";

  return (
    // fills the space between the header and the footer; the negative margins cancel the page padding
    <div className="-mx-4 -my-8 flex h-[calc(100dvh-110px)] min-h-[520px] flex-col lg:-mx-8">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3 lg:px-8">
        <h1 className="text-[15px] font-semibold tracking-tight">Ask the evidence</h1>
        <p className="hidden text-xs text-ink-muted md:block">Answered from completion reports, supervision reports and restructuring papers. Each sentence links to its passage.</p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-2 pt-6 lg:px-8">
        <div className="mx-auto flex max-w-3xl flex-col gap-7">
          {SHOW_INSIGHTS && <InsightsPanel procGroup={procGroup || undefined} countryCode={countryCode || undefined} />}
          {turns.length === 0 && (
            <div className="flex flex-col gap-5 pt-[5vh]">
              <h2 className="bg-gradient-to-r from-foreground via-[#8fa9e6] to-[#7cc9bb] bg-clip-text text-3xl font-semibold leading-tight tracking-tight text-transparent">What do you want to know from past projects?</h2>
              <p className="max-w-[56ch] text-sm text-ink-muted">Answers are built only from quoted evaluation passages. If the reports hold no evidence, you get no answer rather than a guess.</p>
              <div className="grid gap-2.5 sm:grid-cols-3">
                {EXAMPLES.map((e) => (
                  <button key={e.q} onClick={() => send(e.q)}
                    className="flex flex-col gap-1.5 rounded-xl border border-t-2 border-line border-t-brand bg-surface p-3.5 text-left transition hover:-translate-y-px hover:bg-subtle">
                    <span className="text-[11px] font-semibold uppercase tracking-widest text-brand">{e.tag}</span>
                    <span className="text-[13px] leading-snug">{e.q}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t) => (
            <div key={t.id} className="space-y-4">
              <div className="flex justify-end">
                <p className="max-w-[85%] rounded-[18px_18px_4px_18px] bg-gradient-to-br from-brand-strong to-brand-2 px-3.5 py-2 text-sm text-[#f1f4ff]">{t.question}</p>
              </div>
              <div className="flex min-w-0 gap-3">
                <span className="mt-0.5 grid size-[26px] shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-strong to-teal-500 text-white" aria-hidden>
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M2.5 11V5l5.5-3 5.5 3v6L8 14z" /><path d="M8 2v12M2.5 5L8 8l5.5-3" /></svg>
                </span>
                <div className="min-w-0 flex-1">
                  {t.live && !t.response && !t.error && <LiveAnswer live={t.live} />}
                  {t.error && <p className="rounded-lg bg-risk-high-soft px-4 py-3 text-sm text-risk-high">{t.error}</p>}
                  {t.response && <Answer turnId={t.id} r={t.response} question={t.question} />}
                </div>
              </div>
            </div>
          ))}
          <div ref={bottom} />
        </div>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(question);
        }}
        className="px-4 pb-4 pt-2 lg:px-8"
      >
        <div className="mx-auto max-w-3xl rounded-2xl border border-line bg-surface p-2.5 transition focus-within:border-brand focus-within:ring-4 focus-within:ring-brand-soft">
          <div className="mb-1.5 flex flex-wrap gap-2 px-1.5 pt-0.5">
            <select className={select} value={countryCode} onChange={(e) => setCountryCode(e.target.value)} aria-label="Country filter">
              <option value="">All countries</option>
              {opts?.countries.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
            <select className={select} value={procGroup} onChange={(e) => setProcGroup(e.target.value as ProcGroup | "")} aria-label="Procurement type filter">
              <option value="">All procurement types</option>
              {opts?.procGroups.map((g) => (
                <option key={g.code} value={g.code}>
                  {g.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2.5">
            <input
              className="min-w-0 flex-1 bg-transparent px-1.5 py-2 text-sm outline-none placeholder:text-ink-muted"
              placeholder="Ask about past procurement experience…"
              aria-label="Question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
            <button type="submit" disabled={busy || !question.trim()} aria-label="Ask"
              className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-brand disabled:opacity-35">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 13V3M3.5 7.5L8 3l4.5 4.5" /></svg>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

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
