"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { ConversationList, useHistory } from "@/components/history";
import { api } from "@/lib/api/client";
import type { AskResponse, ChatContext, ChatTurn, RankingResponse } from "@/lib/api/types";
import { Answer } from "@/components/ask/answer";
import { LiveAnswer, emptyLive, fold, type Live } from "@/components/ask/live-answer";
import { fmt } from "@/components/dashboard/format";
import { isEvidenceQuestion } from "./route-question";
import { schedule, todayLocal, type PlanPackage } from "@/lib/plan";
import type { PlanState } from "./use-plan";

type Rich =
  | { kind: "plan"; id: string; expiresAt: string; end50: string | null; end90: string | null; bottleneck?: string; packages: number }
  | { kind: "stats"; data: RankingResponse }
  | { kind: "evidence"; question: string; response: AskResponse };
/** content is what the model sees of this message later; rich is what the person sees. */
export interface ChatMsg { id: number; role: "user" | "assistant"; content: string; rich?: Rich; summary?: boolean }

const STARTERS: { kind: "Plan" | "Statistics" | "Evidence"; text: string }[] = [
  { kind: "Plan", text: "I want to plan a roads project in Kenya, about 5 million, then supervision consultants after the works" },
  { kind: "Statistics", text: "Which countries had the slowest awards in the past?" },
  { kind: "Evidence", text: "What usually goes wrong with road works tenders?" },
  { kind: "Plan", text: "Plan a health project in India: medical equipment for 20 million and a training consultancy, all awarded within 18 months" },
];
const KEEP_TURNS = 14;
const KEEP_CHARS = 900;

/** What the model is sent: from the latest summary on (the summary stands in for everything before it), the last KEEP_TURNS. */
const historyFor = (msgs: ChatMsg[]): ChatTurn[] => {
  const at = msgs.map((m) => !!m.summary).lastIndexOf(true);
  const head: ChatTurn[] = at >= 0 ? [{ role: "assistant", content: `Summary of the earlier conversation: ${msgs[at].content}` }] : [];
  return [...head, ...msgs.slice(at + 1).slice(-KEEP_TURNS).map((m) => ({ role: m.role, content: m.content.slice(0, KEEP_CHARS) }))];
};

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

  /** The answer from the reports, streamed. No country or type filter: the question already names what it is about, and
   * filters this narrow made the evidence gate refuse. */
  async function askEvidence(question: string) {
    setBusy("Searching the reports…");
    setLive(emptyLive);
    const response = await api.askStream({ question }, (e) => setLive((l) => (l ? fold(l, e) : l)));
    add({ role: "assistant", rich: { kind: "evidence", question, response },
      content: `${response.unsupported ? "No direct answer in the reports. " : "Answer from the reports: "}${(response.unsupported && response.fallback ? response.fallback.answer : response.answer).map((a) => a.text).join(" ").slice(0, 600)}` });
  }

  async function send(text: string) {
    const clean = text.trim();
    if (!clean || busy || full) return;
    const user: ChatMsg = { id: next.current++, role: "user", content: clean };
    const all = [...msgs, user];
    // a plain question about past projects goes straight to the streaming search; the rest first works out what is wanted
    const direct = isEvidenceQuestion(clean);
    setMsgs(all); setInput(""); setBusy(direct ? "Searching the reports…" : "Understanding your message…");
    try {
      if (direct) { await askEvidence(clean); return; }
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
          const link = await publishPlan({ countryCode: r.plan.countryCode, projectStart: r.plan.projectStart || todayLocal(), deadline: r.plan.deadline ?? undefined,
            packages: pkgs, forecasts: f, plan: p });
          const text = `Forecast ready: typical date for all awards ${p.end50 ?? "unknown"}, slow case ${p.end90 ?? "unknown"}${name ? `; bottleneck ${name}` : ""}.`;
          add({ role: "assistant", content: `${text} The plan is at ${link ? `/shared?id=${link.id}` : "(no link: saving it failed)"}.`,
            rich: link ? { kind: "plan", id: link.id, expiresAt: link.expiresAt, end50: p.end50, end90: p.end90, bottleneck: name, packages: pkgs.length } : undefined });
        }
      } else if (r.intent === "ask_statistics" && r.statistic) {
        setBusy("Looking up the statistics…");
        const data = await api.ranking(r.statistic.measure, r.statistic.group);
        const top = data.rows.filter((x) => !x.few).slice(0, 8);
        add({ role: "assistant", rich: { kind: "stats", data },
          content: `Shown: ${data.measure.label} by ${data.groupLabel}, worst first: ${top.map((x) => `${x.label} ${fmt(data.measure, x.value)}`).join("; ")}.` });
      } else if (r.intent === "ask_evidence" && r.evidenceQuestion) {
        await askEvidence(r.evidenceQuestion);
      }
    } catch (e) {
      add({ role: "assistant", content: `Sorry, that did not work (${(e as Error).message.slice(0, 160)}). You can retry, or edit the plan on its page.` });
    } finally {
      setBusy(""); setLive(null);
    }
  }

  function restart() { history.fresh(); }
  /** Replaces the earlier messages, for the model, with a short summary; the transcript stays on the page. */
  async function compact() {
    if (busy) return;
    setBusy("Summarizing the conversation…");
    try {
      const { summary } = await api.summarizeChat(historyFor(msgs));
      add({ role: "assistant", content: summary, summary: true });
      setCtx(null);   // the next message measures the shorter conversation
    } catch (e) {
      add({ role: "assistant", content: `I could not summarize it (${(e as Error).message.slice(0, 120)}). You can start a new conversation; your plan stays.` });
    } finally {
      setBusy("");
    }
  }
  const pct = ctx ? Math.min(100, Math.round((ctx.used / ctx.budget) * 100)) : 0;
  const empty = msgs.length === 0 && !busy;

  return (
    <div className="flex min-h-0 min-w-0 flex-1">
      <ConversationList h={history} busy={Boolean(busy)} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-8 lg:px-8">
          <div className="mx-auto flex max-w-3xl flex-col gap-7 text-[15px] leading-relaxed">
            {empty && (
              <div className="flex flex-col gap-6 pt-[6vh]">
                <div className="space-y-2">
                  <h2 className="text-2xl font-semibold text-brand-strong">What are you planning?</h2>
                  <p className="max-w-[60ch] text-ink-muted">Describe a project&apos;s packages and I will forecast each one from comparable World Bank packages and give you the plan as a page you can edit and export. You can also ask what went wrong in past projects, in any country.</p>
                </div>
                <div className="divide-y divide-line border-y border-line">
                  {STARTERS.map((t) => (
                    <button key={t.text} type="button" onClick={() => void send(t.text)}
                      className="flex w-full items-start gap-3 px-1 py-3 text-left transition-colors hover:bg-subtle">
                      <span className="w-20 shrink-0 pt-0.5 text-xs text-ink-muted">{t.kind}</span>
                      <span className="text-sm">{t.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m) => m.summary ? (
              <details key={m.id} className="border-l-2 border-line pl-3 text-xs text-ink-muted">
                <summary className="cursor-pointer">Earlier messages were summarized to make room. Show the summary</summary>
                <p className="mt-2 whitespace-pre-wrap text-foreground">{m.content}</p>
              </details>
            ) : m.role === "user" ? (
              <div key={m.id} className="flex justify-end">
                <p className="max-w-[80%] whitespace-pre-wrap rounded-lg bg-subtle px-4 py-2.5">{m.content}</p>
              </div>
            ) : (
              <div key={m.id} className="min-w-0 space-y-3">
                {m.rich?.kind === "plan" ? <PlanLink r={m.rich} text={m.content} />
                  : m.rich?.kind === "stats" ? <StatsTable data={m.rich.data} />
                  : m.rich?.kind === "evidence" ? <div className="space-y-2"><p className="text-xs text-ink-muted">{m.rich.question}</p><Answer turnId={1000 + m.id} r={m.rich.response} question={m.rich.question} /></div>
                  : <p className="whitespace-pre-wrap">{m.content}</p>}
              </div>
            ))}
            {(live || busy) && (
              <div className="min-w-0">
                {live ? <LiveAnswer live={live} /> : (
                  <p className="flex items-center gap-2 text-sm text-ink-muted"><Loader2 size={14} className="animate-spin" aria-hidden />{s.running && s.progress ? s.progress : busy}</p>
                )}
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>
        <div className="px-4 pb-5 pt-1 lg:px-8">
          <div className="mx-auto max-w-3xl space-y-2">
            {ctx?.warn && !full && (
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-risk-medium">
                <span>This conversation is getting long ({pct}% of what the model can hold).</span>
                <button className="underline underline-offset-2" onClick={() => void compact()} disabled={Boolean(busy)}>Summarize and continue</button>
                <button className="underline underline-offset-2" onClick={restart}>Start a new one</button>
              </p>
            )}
            {full ? (
              <div className="flex items-center justify-between gap-3 rounded-lg border border-line px-4 py-3 text-sm">
                <span>This conversation has reached the model&apos;s length limit.</span>
                <span className="flex shrink-0 gap-2">
                  <button className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium" onClick={() => void compact()} disabled={Boolean(busy)}>Summarize and continue</button>
                  <button className="rounded-md border border-line px-3 py-1.5" onClick={restart}>Start a new one</button>
                </span>
              </div>
            ) : (
              <form className="flex items-end gap-2 rounded-lg border border-line bg-surface p-2 pl-4 transition-colors focus-within:border-brand-2"
                onSubmit={(e) => { e.preventDefault(); void send(input); }}>
                <textarea className="max-h-40 min-w-0 flex-1 resize-none bg-transparent py-2 text-[15px] leading-snug outline-none placeholder:text-ink-muted" rows={1}
                  placeholder="Describe what you want to plan, or ask about past projects…" aria-label="Message" value={input} maxLength={1500} disabled={Boolean(busy)}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(input); } }} />
                {pct >= 50 && <span className={`mb-2.5 shrink-0 text-[11px] ${pct >= 70 ? "text-risk-medium" : "text-ink-muted"}`} title="How much of what the model can hold this conversation uses">{pct}% full</span>}
                <button type="submit" disabled={Boolean(busy) || !input.trim()} aria-label="Send"
                  className="grid size-9 shrink-0 place-items-center rounded-md bg-brand transition-opacity disabled:opacity-30">
                  <ArrowUp size={16} aria-hidden />
                </button>
              </form>
            )}
            <p className="text-center text-[11px] text-ink-muted">Forecasts come from past World Bank packages and every answer cites its source report. Check them before you rely on them.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatsTable({ data }: { data: RankingResponse }) {
  const rows = data.rows.slice(0, 10);
  return (
    <div className="space-y-1.5">
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

const LINK_KEY = "procintel-plan-link";

/** Save the chat's plan behind its link: the same link as before when this browser made it (so an open plan page shows
 * the update), a new one otherwise. Returns the link, or null when saving failed. */
async function publishPlan(body: unknown): Promise<{ id: string; expiresAt: string } | null> {
  let id: string | null = null;
  try { id = localStorage.getItem(LINK_KEY); } catch { /* storage blocked */ }
  try {
    if (id) {
      const out = await api.updateShare(id, body);
      if (!("error" in out)) return out;
    }
  } catch { /* expired or not ours: make a new one */ }
  try {
    const made = await api.createShare("plan", body);
    if ("error" in made) return null;
    try { localStorage.setItem(LINK_KEY, made.id); } catch { /* storage blocked */ }
    return made;
  } catch {
    return null;
  }
}

/** The chat's answer to a plan change: a card with the dates and the link that opens the plan on its own page. */
function PlanLink({ r, text }: { r: Extract<Rich, { kind: "plan" }>; text: string }) {
  return (
    <div className="space-y-2">
      <p className="whitespace-pre-wrap">{text.replace(/ The plan is at \S+\.$/, "")}</p>
      <a href={`/shared?id=${r.id}`} target="_blank" rel="noreferrer"
        className="flex items-center justify-between gap-3 rounded-xl border border-brand/40 bg-brand-soft px-4 py-3 hover:border-brand">
        <span>
          <span className="block font-medium">Procurement plan · {r.packages} package{r.packages === 1 ? "" : "s"}</span>
          <span className="block text-xs text-ink-muted">All awarded by {r.end50 ?? "?"} (slow case {r.end90 ?? "?"}){r.bottleneck ? ` · bottleneck ${r.bottleneck}` : ""}</span>
        </span>
        <span className="shrink-0 text-xs font-medium text-brand">Open, edit or export →</span>
      </a>
      <p className="text-[11px] text-ink-muted">The link shows the latest version of this plan until {new Date(r.expiresAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}.</p>
    </div>
  );
}
