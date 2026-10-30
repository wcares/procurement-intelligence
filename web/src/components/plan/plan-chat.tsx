"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { HistoryMenu, useHistory } from "@/components/history";
import { api } from "@/lib/api/client";
import type { AskResponse, ChatContext, ChatTurn, RankingResponse } from "@/lib/api/types";
import { Answer } from "@/app/ask/ask-view";
import { LiveAnswer, emptyLive, fold, type Live } from "@/components/ask/live-answer";
import { fmt } from "@/components/dashboard/format";
import { schedule, todayLocal, type PlanPackage } from "@/lib/plan";
import type { PlanState } from "./use-plan";

type Rich =
  | { kind: "stats"; data: RankingResponse }
  | { kind: "evidence"; question: string; response: AskResponse };
/** content is what the model sees of this message later; rich is what the person sees. */
export interface ChatMsg { id: number; role: "user" | "assistant"; content: string; rich?: Rich }

const STARTERS: { kind: "Plan" | "Statistics" | "Evidence"; text: string }[] = [
  { kind: "Plan", text: "I want to plan a roads project in Kenya, about 5 million, then supervision consultants after the works" },
  { kind: "Statistics", text: "Which countries had the slowest awards in the past?" },
  { kind: "Evidence", text: "What usually goes wrong with road works tenders?" },
  { kind: "Plan", text: "Plan a health project in India: medical equipment for 20 million and a training consultancy, all awarded within 18 months" },
];
const KIND_COLOR = { Plan: "border-t-brand text-brand", Statistics: "border-t-risk-low text-risk-low", Evidence: "border-t-risk-medium text-risk-medium" } as const;
const KEEP_TURNS = 14;
const KEEP_CHARS = 900;

const historyFor = (msgs: ChatMsg[]): ChatTurn[] =>
  msgs.slice(-KEEP_TURNS).map((m) => ({ role: m.role, content: m.content.slice(0, KEEP_CHARS) }));

/** The planning chat: say what you want to plan, answer its questions, ask about the plan or about the past. The plan
 * on the right is the same one the manual tab edits. The conversation lives in this page only. */
export function PlanChat({ s }: { s: PlanState }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState("");
  const [live, setLive] = useState<Live | null>(null);   // an evidence answer being written
  const [ctx, setCtx] = useState<ChatContext | null>(null);
  const next = useRef(1);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, busy, live]);

  // saved on the server per user: reopened after a reload, listed under History, continued by opening one
  const restore = useCallback((saved: ChatMsg[]) => {
    setMsgs(saved);
    next.current = saved.reduce((m, x) => Math.max(m, x.id), 0) + 1;
    setCtx(null); setInput("");
  }, []);
  const history = useHistory<ChatMsg>("plan", msgs, restore, Boolean(busy));

  const add = (m: Omit<ChatMsg, "id">) => setMsgs((all) => [...all, { ...m, id: next.current++ }]);
  const full = ctx?.full ?? false;

  async function send(text: string) {
    const clean = text.trim();
    if (!clean || busy || full) return;
    const user: ChatMsg = { id: next.current++, role: "user", content: clean };
    const all = [...msgs, user];
    setMsgs(all); setInput(""); setBusy("Thinking…");
    try {
      const r = await api.planChat(historyFor(all), s.asChatPlan(), s.results);
      setCtx(r.context);
      add({ role: "assistant", content: r.reply });
      if (r.intent === "update_plan" && r.changes.length) {
        s.adopt(r.plan);
        if (r.plan.countryCode && r.plan.packages.length) {
          const pkgs = r.plan.packages as PlanPackage[];
          const f = await s.run(pkgs, r.plan.countryCode);
          const p = schedule(pkgs, f, r.plan.projectStart || todayLocal());
          const name = pkgs.find((x) => x.id === p.bottleneck)?.name;
          add({ role: "assistant", content: `Forecast ready: typical date for all awards ${p.end50 ?? "unknown"}, slow case ${p.end90 ?? "unknown"}${name ? `; bottleneck ${name}` : ""}. The plan is on the right.` });
        }
      } else if (r.intent === "ask_statistics" && r.statistic) {
        setBusy("Looking up the statistics…");
        const data = await api.ranking(r.statistic.measure, r.statistic.group);
        const top = data.rows.filter((x) => !x.few).slice(0, 8);
        add({ role: "assistant", rich: { kind: "stats", data },
          content: `Shown: ${data.measure.label} by ${data.groupLabel}, worst first: ${top.map((x) => `${x.label} ${fmt(data.measure, x.value)}`).join("; ")}.` });
      } else if (r.intent === "ask_evidence" && r.evidenceQuestion) {
        setBusy("Searching the reports…");
        // no country or type filter: the question already names what it is about, and filters this narrow made the evidence gate refuse
        setLive(emptyLive);
        const response = await api.askStream({ question: r.evidenceQuestion }, (e) => setLive((l) => (l ? fold(l, e) : l)));
        add({ role: "assistant", rich: { kind: "evidence", question: r.evidenceQuestion, response },
          content: `${response.unsupported ? "No direct answer in the reports. " : "Answer from the reports: "}${(response.unsupported && response.fallback ? response.fallback.answer : response.answer).map((a) => a.text).join(" ").slice(0, 600)}` });
      }
    } catch (e) {
      add({ role: "assistant", content: `Sorry, that did not work (${(e as Error).message.slice(0, 160)}). You can retry, or use the Manual tab.` });
    } finally {
      setBusy(""); setLive(null);
    }
  }

  function restart() { history.fresh(); }
  const pct = ctx ? Math.min(100, Math.round((ctx.used / ctx.budget) * 100)) : 0;
  const empty = msgs.length === 0 && !busy;

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-2 pt-6 lg:px-8">
        <div className="mx-auto flex max-w-2xl flex-col gap-6 text-sm">
          {empty && (
            <div className="flex flex-col gap-5 pt-[4vh]">
              <h2 className="bg-gradient-to-r from-foreground via-[#8fa9e6] to-[#7cc9bb] bg-clip-text text-3xl font-semibold leading-tight tracking-tight text-transparent">What are you planning?</h2>
              <p className="max-w-[52ch] text-ink-muted">Tell me what you want to plan. I will ask for what is missing, forecast it, and you can keep talking: change a method, ask about the risks, or ask what went wrong in past projects.</p>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {STARTERS.map((t) => (
                  <button key={t.text} type="button" onClick={() => void send(t.text)}
                    className={`flex flex-col gap-1.5 rounded-xl border border-t-2 border-line bg-surface p-3.5 text-left transition hover:-translate-y-px hover:bg-subtle ${KIND_COLOR[t.kind]}`}>
                    <span className="text-[11px] font-semibold uppercase tracking-widest">{t.kind}</span>
                    <span className="text-[13px] leading-snug text-foreground">{t.text}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m) => m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-[18px_18px_4px_18px] bg-gradient-to-br from-brand-strong to-brand-2 px-3.5 py-2 text-[#f1f4ff]">{m.content}</p>
            </div>
          ) : (
            <div key={m.id} className="flex min-w-0 gap-3">
              <Mark />
              <div className="min-w-0 flex-1 space-y-2.5">
                {m.rich?.kind === "stats" ? <StatsTable data={m.rich.data} />
                  : m.rich?.kind === "evidence" ? <div className="space-y-2"><p className="text-xs text-ink-muted">{m.rich.question}</p><Answer turnId={1000 + m.id} r={m.rich.response} question={m.rich.question} /></div>
                  : <p className="whitespace-pre-wrap">{m.content}</p>}
              </div>
            </div>
          ))}
          {(live || busy) && (
            <div className="flex min-w-0 gap-3">
              <Mark />
              <div className="min-w-0 flex-1">
                {live ? <LiveAnswer live={live} /> : (
                  <p className="flex items-center gap-2 text-ink-muted"><span className="inline-block size-2 animate-pulse rounded-full bg-brand" aria-hidden />{s.running && s.progress ? s.progress : busy}</p>
                )}
              </div>
            </div>
          )}
          <div ref={bottom} />
        </div>
      </div>
      {ctx?.warn && !full && (
        <p className="mx-4 mb-2 rounded-lg bg-risk-medium-soft px-3 py-2 text-xs text-risk-medium lg:mx-8">This conversation is getting long ({pct}% of what the model can hold). Start a new one soon; your plan stays.</p>
      )}
      <div className="px-4 pb-4 pt-2 lg:px-8">
        {full ? (
          <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 rounded-2xl border border-line bg-surface px-4 py-3 text-sm">
            <span>This conversation has reached the model&apos;s length limit.</span>
            <button className="rounded-lg bg-brand px-3 py-1.5 font-medium" onClick={restart}>Start a new conversation</button>
          </div>
        ) : (
          <form className="mx-auto flex max-w-2xl items-end gap-2.5 rounded-2xl border border-line bg-surface py-2.5 pl-4 pr-2.5 transition focus-within:border-brand focus-within:ring-4 focus-within:ring-brand-soft"
            onSubmit={(e) => { e.preventDefault(); void send(input); }}>
            <textarea className="max-h-32 min-w-0 flex-1 resize-none bg-transparent py-1.5 text-sm leading-snug outline-none placeholder:text-ink-muted" rows={1}
              placeholder="Describe what you want to plan, or ask a question…" aria-label="Message" value={input} maxLength={1500} disabled={Boolean(busy)}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(input); } }} />
            {pct >= 50 && <span className={`mb-2 shrink-0 text-[11px] ${pct >= 70 ? "text-risk-medium" : "text-ink-muted"}`} title="How much of what the model can hold this conversation uses">{pct}% full</span>}
            <button type="submit" disabled={Boolean(busy) || !input.trim()} aria-label="Send"
              className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-brand disabled:opacity-35">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M8 13V3M3.5 7.5L8 3l4.5 4.5" /></svg>
            </button>
          </form>
        )}
        <div className="mx-auto mt-2 flex max-w-2xl items-center justify-between gap-3 text-[11.5px] text-ink-muted">
          <HistoryMenu h={history} />
          {msgs.length > 0 && <button className="underline underline-offset-2" onClick={restart}>New conversation</button>}
        </div>
      </div>
    </div>
  );
}

function Mark() {
  return (
    <span className="mt-0.5 grid size-[26px] shrink-0 place-items-center rounded-lg bg-gradient-to-br from-brand-strong to-teal-500 text-white" aria-hidden>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M2.5 11V5l5.5-3 5.5 3v6L8 14z" /><path d="M8 2v12M2.5 5L8 8l5.5-3" /></svg>
    </span>
  );
}

function StatsTable({ data }: { data: RankingResponse }) {
  const rows = data.rows.slice(0, 10);
  return (
    <div className="space-y-1.5 rounded-xl border border-line bg-surface p-3.5">
      <p className="text-xs font-semibold">{data.measure.label}, by {data.groupLabel.toLowerCase()} (worst first)</p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-ink-muted"><tr><th className="pr-2">{data.groupLabel}</th><th className="pr-2">Value</th><th className="pr-2">Projects</th><th>Based on</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className={`border-t border-line ${r.few ? "text-ink-muted" : ""}`}>
                <td className="py-0.5 pr-2">{r.label}</td><td className="pr-2 tabular-nums">{fmt(data.measure, r.value)}</td>
                <td className="pr-2 tabular-nums">{r.projects}</td><td className="tabular-nums">{r.n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-ink-muted">Greyed rows rest on fewer than 3 projects. {data.measure.note}</p>
    </div>
  );
}
