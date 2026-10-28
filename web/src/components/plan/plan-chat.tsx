"use client";

import { useEffect, useRef, useState } from "react";
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

const STARTERS = [
  "I want to plan a roads project in Kenya, about 5 million, then supervision consultants after the works",
  "Which countries had the slowest awards in the past?",
  "What usually goes wrong with road works tenders?",
  "Plan a health project in India: medical equipment for 20 million and a training consultancy, all awarded within 18 months",
];
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
          content: response.unsupported ? "The reports hold no evidence for that question." : `Answer from the reports: ${response.answer.map((a) => a.text).join(" ").slice(0, 600)}` });
      }
    } catch (e) {
      add({ role: "assistant", content: `Sorry, that did not work (${(e as Error).message.slice(0, 160)}). You can retry, or use the Manual tab.` });
    } finally {
      setBusy(""); setLive(null);
    }
  }

  function restart() { setMsgs([]); setCtx(null); setInput(""); }
  const pct = ctx ? Math.min(100, Math.round((ctx.used / ctx.budget) * 100)) : 0;

  return (
    <div className="flex min-h-[28rem] flex-col rounded-xl border border-line bg-surface">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2 text-xs text-ink-muted">
        <span>Planning assistant · the conversation is kept on this page only</span>
        {msgs.length > 0 && <button className="underline" onClick={restart}>New conversation</button>}
      </div>
      <div className="max-h-[60vh] flex-1 space-y-3 overflow-y-auto p-4 text-sm">
        {msgs.length === 0 && (
          <div className="space-y-3">
            <p className="text-ink-muted">Tell me what you want to plan. I will ask for what is missing, forecast it, and you can keep
              talking: change a method, ask about the risks, or ask what went wrong in past projects.</p>
            <div className="flex flex-col gap-2">
              {STARTERS.map((t) => (
                <button key={t} type="button" onClick={() => void send(t)} className="rounded-lg border border-line px-3 py-2 text-left text-xs hover:bg-subtle">{t}</button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[92%] min-w-0 space-y-2 rounded-xl px-3 py-2 ${m.role === "user" ? "bg-brand text-white dark:text-black" : "bg-subtle"}`}>
              {m.rich?.kind === "stats" ? <StatsTable data={m.rich.data} />
                : m.rich?.kind === "evidence" ? <div className="space-y-2"><p className="text-xs text-ink-muted">{m.rich.question}</p><Answer turnId={1000 + m.id} r={m.rich.response} question={m.rich.question} /></div>
                : <p className="whitespace-pre-wrap">{m.content}</p>}
            </div>
          </div>
        ))}
        {live ? <div className="max-w-[92%] rounded-xl bg-subtle px-3 py-2"><LiveAnswer live={live} /></div>
          : busy && <p className="text-xs text-ink-muted">{s.running && s.progress ? s.progress : busy}</p>}
        <div ref={bottom} />
      </div>
      {ctx?.warn && !full && (
        <p className="border-t border-line px-4 py-1.5 text-xs text-risk-medium">This conversation is getting long ({pct}% of what the model can hold). Start a new one soon; your plan stays.</p>
      )}
      {full ? (
        <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-sm">
          <span>This conversation has reached the model&apos;s length limit.</span>
          <button className="rounded-md bg-brand px-3 py-1.5 text-white dark:text-black" onClick={restart}>Start a new conversation</button>
        </div>
      ) : (
        <form className="flex gap-2 border-t border-line p-3" onSubmit={(e) => { e.preventDefault(); void send(input); }}>
          <input className="min-w-0 flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand" placeholder="Describe what you want to plan, or ask a question…"
            value={input} maxLength={1500} onChange={(e) => setInput(e.target.value)} disabled={Boolean(busy)} />
          <button type="submit" disabled={Boolean(busy) || !input.trim()} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-black">Send</button>
        </form>
      )}
    </div>
  );
}

function StatsTable({ data }: { data: RankingResponse }) {
  const rows = data.rows.slice(0, 10);
  return (
    <div className="space-y-1">
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
