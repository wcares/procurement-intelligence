"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Loader2, MessageCircle, X } from "lucide-react";
import { api } from "@/lib/api/client";
import type { AskResponse, AssessRequest, AssessResponse, ChatPlan, ChatTurn, RankingResponse } from "@/lib/api/types";
import { Answer } from "@/components/ask/answer";
import { StatsTable } from "@/components/plan/plan-chat";

interface Msg { id: number; role: "user" | "assistant"; content: string; answer?: AskResponse; steps?: string[]; stats?: RankingResponse; question?: string }

const STARTERS = ["Why could this package be slow?", "What can I do to award it faster?", "What went wrong on similar projects?"];
const KEEP_TURNS = 12;

/** What the assessment showed, in words the assistant can use and check its figures against (the chat's `results`). */
export function assessmentText(req: AssessRequest, r: AssessResponse): string {
  const lines = [`ASSESSMENT of the package: ${req.procGroup} by ${req.methodCode} in ${req.countryCode}` +
    `${req.estimatedValueUsd ? `, US$${req.estimatedValueUsd.toLocaleString("en-US")}` : ""}${req.description ? `, "${req.description}"` : ""}` +
    `${req.projectId ? `, project ${req.projectId}` : ""}.`];
  if (r.timeline) lines.push(`Days from tender notice to award, comparable packages (${r.timeline.scope}, ${r.timeline.n} packages): ` +
    `median ${r.timeline.median}, quartiles ${r.timeline.p25} to ${r.timeline.p75}, slow case (1 in 10) ${r.timeline.p90}.`);
  if (r.prediction) lines.push(`This package: ${r.prediction.days_p50} days (${r.prediction.basis})` +
    `${r.prediction.days_p90 != null ? `, slow case ${r.prediction.days_p90}` : ""}` +
    `${r.prediction.p_long != null ? `, chance of over 180 days ${Math.round(r.prediction.p_long * 100)}%` : ""}.`);
  for (const s of r.stages ?? []) if (s.median != null) lines.push(`Stage "${s.label}": median ${s.median} days, slow case ${s.p90 ?? "?"} (${s.n} packages).`);
  for (const f of r.risks) lines.push(`Risk (${f.level}, ${f.basis}): ${f.label}. ${f.detail}`);
  for (const p of r.precedents.slice(0, 6)) lines.push(`Lesson from ${p.citation.projectName} (${p.citation.projectId}), ${p.citation.section}: "${p.citation.quote.slice(0, 220)}"`);
  for (const s of r.similarPackages.slice(0, 5)) lines.push(`Similar past package ${s.packageId} (${s.countryCode}): "${s.description}", ${s.tenderToAwardDays ?? "unknown"} days to award` +
    `${s.valueUsd ? `, US$${Math.round(s.valueUsd).toLocaleString("en-US")}` : ""}.`);
  return lines.join("\n").slice(0, 11000);   // the backend takes 12,000 characters
}

/** The package as a one-package plan, so the assistant's plan tools see it. */
function asPlan(req: AssessRequest): ChatPlan {
  return { countryCode: req.countryCode, projectStart: null, deadline: null, packages: [{
    id: "assessed", name: req.description || `${req.procGroup} by ${req.methodCode}`, procGroup: req.procGroup, methodCode: req.methodCode,
    sector: req.sector, estimatedValueUsd: req.estimatedValueUsd, description: req.description }] };
}

/** A floating chat on the Assess tab, like a support widget: the assistant knows the package and everything the
 * assessment showed (assessmentText), and answers with sources like the planning chat. The conversation lives in the
 * panel only and starts over with a new assessment. */
export function AssessChat({ request, result }: { request: AssessRequest; result: AssessResponse }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const next = useRef(1);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { setMsgs([]); }, [result]);   // a new assessment: a new conversation
  useEffect(() => { if (open) bottom.current?.scrollIntoView({ block: "end" }); }, [msgs, busy, open]);

  async function send(text: string) {
    const clean = text.trim();
    if (!clean || busy) return;
    const all = [...msgs, { id: next.current++, role: "user" as const, content: clean }];
    setMsgs(all); setInput(""); setBusy(true);
    try {
      const history: ChatTurn[] = all.slice(-KEEP_TURNS).map((m) => ({ role: m.role, content: m.content.slice(0, 900) }));
      // the same backend and tools as the planning chat; the routes a model without tools uses are handled here too
      const r = await api.planChat(history, asPlan(request), assessmentText(request, result));
      const add = (m: Omit<Msg, "id">) => setMsgs((all) => [...all, { ...m, id: next.current++ }]);
      if (r.intent === "ask_evidence" && r.evidenceQuestion) {
        const a = await api.ask({ question: r.evidenceQuestion });
        add({ role: "assistant", content: a.answer.map((s) => s.text).join(" ").slice(0, 600), answer: a, question: r.evidenceQuestion });
      } else if (r.intent === "ask_statistics" && r.statistic) {
        const data = await api.ranking(r.statistic.measure, r.statistic.group);
        add({ role: "assistant", content: `Shown: ${data.measure.label} by ${data.groupLabel}.`, stats: data });
      } else {
        add({ role: "assistant", content: r.reply, answer: r.intent === "chat" ? r.answer : undefined, steps: r.steps });
      }
      for (const data of r.statistics ?? []) add({ role: "assistant", content: `Shown: ${data.measure.label} by ${data.groupLabel}.`, stats: data });
    } catch (e) {
      setMsgs((m) => [...m, { id: next.current++, role: "assistant", content: `Sorry, that did not work (${(e as Error).message.slice(0, 120)}). Please try again.` }]);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} aria-label="Ask about this package"
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full bg-brand px-4 py-3 text-sm font-medium text-on-brand shadow-lg hover:opacity-90 print:hidden">
        <MessageCircle size={18} aria-hidden /> Ask about this package
      </button>
    );
  }
  return (
    <div role="dialog" aria-label="Ask about this package"
      className="fixed bottom-0 right-0 z-40 flex h-full w-full flex-col border-l border-line bg-surface shadow-2xl sm:bottom-6 sm:right-6 sm:h-[min(42rem,calc(100vh-3rem))] sm:w-[28rem] sm:rounded-xl sm:border print:hidden">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <p className="font-medium">Ask about this package</p>
          <p className="truncate text-xs text-ink-muted">{request.description || `${request.procGroup} by ${request.methodCode}`} · {request.countryCode}</p>
        </div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close" className="rounded-md p-1 hover:bg-subtle"><X size={18} aria-hidden /></button>
      </div>
      <div className="min-w-0 flex-1 space-y-4 overflow-y-auto px-4 py-4 text-sm">
        {msgs.length === 0 && (
          <div className="space-y-2">
            <p className="text-ink-muted">The assistant knows this package and what the assessment showed. Try:</p>
            {STARTERS.map((t) => (
              <button key={t} type="button" onClick={() => void send(t)} className="block w-full rounded-md border border-line px-3 py-2 text-left hover:bg-subtle">{t}</button>
            ))}
          </div>
        )}
        {msgs.map((m) => m.role === "user" ? (
          <div key={m.id} className="flex justify-end"><p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-subtle px-3 py-2">{m.content}</p></div>
        ) : (
          <div key={m.id} className="min-w-0">
            {m.stats ? <StatsTable data={m.stats} />
              : m.answer ? <Answer turnId={5000 + m.id} r={m.answer} question={m.question ?? ""} steps={m.steps} />
              : <p className="whitespace-pre-wrap">{m.content}</p>}
          </div>
        ))}
        {busy && <p className="flex items-center gap-2 text-ink-muted"><Loader2 size={14} className="animate-spin" aria-hidden /> Thinking…</p>}
        <div ref={bottom} />
      </div>
      <form className="flex items-end gap-2 border-t border-line p-3" onSubmit={(e) => { e.preventDefault(); void send(input); }}>
        <textarea className="max-h-32 min-w-0 flex-1 resize-none rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand-2" rows={1}
          placeholder="Ask about this package…" aria-label="Message" value={input} maxLength={1500} disabled={busy}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(input); } }} />
        <button type="submit" disabled={busy || !input.trim()} aria-label="Send"
          className="grid size-9 shrink-0 place-items-center rounded-md bg-brand text-on-brand disabled:opacity-30"><ArrowUp size={16} aria-hidden /></button>
      </form>
    </div>
  );
}
