"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { AskResponse, Options, ProcGroup } from "@/lib/api/types";
import { Caveats, CitationCard } from "@/components/evidence";
import { FeedbackBar, FlagCitation } from "@/components/feedback";
import { AnswerMap } from "@/components/ask/answer-map";
import { InsightsPanel } from "@/components/insights/insights-panel";

type Turn = { id: number; question: string; response?: AskResponse; error?: string };

const EXAMPLES = [
  "Why were procurement processes cancelled or contracts terminated?",
  "What caused delays in civil works contracts?",
  "What lessons were learned about procurement capacity of implementing agencies?",
];

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
    setTurns((t) => [...t, { id, question: text }]);
    setQuestion("");
    setBusy(true);
    try {
      const response = await api.ask({ question: text, countryCode: countryCode || undefined, procGroup: procGroup || undefined });
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, response } : x)));
    } catch (e) {
      setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: (e as Error).message } : x)));
    } finally {
      setBusy(false);
    }
  }

  const select = "rounded-md border border-line bg-surface px-2 py-1.5 text-sm";

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <InsightsPanel procGroup={procGroup || undefined} countryCode={countryCode || undefined} />
      </div>
      <div className="space-y-8">
        {turns.length === 0 && (
          <div className="rounded-xl border border-dashed border-line p-6">
            <p className="mb-3 text-sm text-ink-muted">Answers are built only from quoted evaluation passages. Try:</p>
            <div className="flex flex-col gap-2">
              {EXAMPLES.map((e) => (
                <button key={e} onClick={() => send(e)} className="rounded-md bg-subtle px-3 py-2 text-left text-sm hover:bg-brand-soft">
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((t) => (
          <div key={t.id} className="space-y-3">
            <div className="ml-auto w-fit max-w-[85%] rounded-xl bg-brand px-4 py-2 text-sm text-white dark:text-black">{t.question}</div>
            {!t.response && !t.error && <p className="text-sm text-ink-muted">Searching the evaluations…</p>}
            {t.error && <p className="rounded-lg bg-risk-high-soft px-4 py-3 text-sm text-risk-high">{t.error}</p>}
            {t.response && <Answer turnId={t.id} r={t.response} question={t.question} />}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(question);
        }}
        className="sticky bottom-4 mt-8 rounded-xl border border-line bg-surface p-3 shadow-sm"
      >
        <div className="mb-2 flex flex-wrap gap-2">
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
        <div className="flex gap-2">
          <input
            className="min-w-0 flex-1 rounded-md border border-line bg-background px-3 py-2 text-sm outline-none focus:border-brand"
            placeholder="Ask about past procurement experience…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <button type="submit" disabled={busy || !question.trim()} className="rounded-md bg-brand px-4 text-sm font-medium text-white disabled:opacity-50 dark:text-black">
            Ask
          </button>
        </div>
      </form>
    </div>
  );
}

function Answer({ turnId, r, question }: { turnId: number; r: AskResponse; question: string }) {
  const [asMap, setAsMap] = useState(false);
  const toSource = (i: number) => {
    const el = document.getElementById(`t${turnId}-c${i}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.classList.add("ring-2", "ring-brand", "rounded-xl");
    setTimeout(() => el?.classList.remove("ring-2", "ring-brand"), 1500);
  };
  if (r.unsupported) {
    return (
      <div className="space-y-2">
        <p className="rounded-xl border border-line bg-surface px-4 py-3 text-sm">
          The evaluation documents in the current dataset don&apos;t contain evidence for this question, so there is no answer
          rather than a guess. Try rephrasing, or removing the filters.
        </p>
        <Caveats meta={r.meta} />
        <FeedbackBar responseId={r.meta.responseId} subject="answer" />
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <button className="text-xs text-ink-muted underline" onClick={() => setAsMap(!asMap)}>{asMap ? "Show as text" : "Show as map"}</button>
      {asMap && <AnswerMap r={r} question={question} onSource={toSource} />}
      <div className="rounded-xl border border-line bg-surface px-4 py-3 text-sm leading-relaxed">
        {r.answer.map((s, i) => (
          <span key={i}>
            {s.text}{" "}
            {s.citations.map((c) => (
              <a key={c} href={`#t${turnId}-c${c}`} className="font-mono text-xs font-semibold text-brand hover:underline">
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
      <Caveats meta={r.meta} />
      <FeedbackBar responseId={r.meta.responseId} subject="answer" />
    </div>
  );
}
