"use client";

import { useState } from "react";
import { api } from "@/lib/api/client";
import type { EvalRun, EvaluationResponse, PromptEvalSide, RetrievalScores } from "@/lib/api/types";
import { localTime, MEASURES, pct, ratio } from "./measures";

type Comparisons = EvaluationResponse["comparisons"];

/** Live against an alternative, measure by measure: shadow index builds (build, evaluate, promote, discard), candidate
 * prompt versions (activate) and runs with another model (for reading only). */
export function ComparisonsView({ data, onChanged }: { data: Comparisons; onChanged: () => void }) {
  const [note, setNote] = useState<string | null>(null);
  async function act(f: () => Promise<unknown>, done: string) {
    try {
      const r = (await f()) as { note?: string | null } | undefined;
      setNote(r?.note ?? done);
      onChanged();
    } catch (e) {
      setNote((e as Error).message);
    }
  }
  const idle = data.shadowKinds.filter((k) => !data.shadows.some((s) => s.name === k.name && s.status !== "discarded"));
  return (
    <div className="space-y-4">
      {note && <p className="text-xs text-muted">{note}</p>}
      {data.shadows.filter((s) => s.status !== "discarded").map((s) => (
        <Card key={s.name} title={`Shadow index: ${s.label}`} status={s.status}>
          {s.note && <p className="mb-2 text-xs text-muted">{s.note}</p>}
          {s.metrics ? (
            <Side rows={[
              ["Search precision (top 5)", s.metrics.live.hybrid_p5, s.metrics.shadow.hybrid_p5],
              ["Search recall (top 10)", s.metrics.live.hybrid_r10, s.metrics.shadow.hybrid_r10],
              ["Keyword precision (top 5)", s.metrics.live.bm25_p5, s.metrics.shadow.bm25_p5],
              ["Keyword recall (top 10)", s.metrics.live.bm25_r10, s.metrics.shadow.bm25_r10],
            ]} left="live" right="shadow" footer={`${(s.metrics.live as RetrievalScores).questions} questions · passages ${s.metrics.passages.live} → ${s.metrics.passages.shadow}`} />
          ) : <p className="text-xs text-muted">Not evaluated yet.</p>}
          <div className="mt-2 flex gap-2 text-xs">
            {s.status === "built" && <Btn onClick={() => act(() => api.shadowAction(s.name, "evaluate"), "Evaluation queued.")}>Evaluate</Btn>}
            {s.status === "evaluated" && <Btn onClick={() => act(() => api.shadowAction(s.name, "promote"), "Promotion queued.")}>Promote</Btn>}
            {s.status !== "promoted" && <Btn onClick={() => act(() => api.shadowAction(s.name, "discard"), "Discarded.")}>Discard</Btn>}
          </div>
        </Card>
      ))}
      {idle.length > 0 && (
        <p className="text-xs text-muted">
          Shadow builds available:{" "}
          {idle.map((k) => (
            <button key={k.name} className="mr-2 underline" onClick={() => act(() => api.shadowAction(k.name, "build"), "Build queued (background).")}>
              build {k.label.toLowerCase()}
            </button>
          ))}
        </p>
      )}
      {data.prompts.map((p) => (
        <Card key={`${p.name}:${p.version}`} title={`Prompt: ${p.label}, v${p.version}`} status={p.note ?? "candidate"}>
          <Side rows={sides(p.evaluation.active, p.evaluation.candidate)} left={`active v${p.evaluation.versions.active}`} right={`v${p.version}`} />
          <div className="mt-2 text-xs">
            <Btn onClick={() => act(() => api.activatePrompt(p.name, p.version), `Version ${p.version} is active.`)}>Activate v{p.version}</Btn>
          </div>
        </Card>
      ))}
      {data.models.map((m) => (
        <Card key={m.name} title={`Another model: ${m.name}`} status={`run ${localTime(m.run.time)}`}>
          <Side rows={MEASURES.map((x) => [x.label, m.live ? x.value(m.live) : null, x.value(m.run)] as Row)}
            left={m.live ? `live (${localTime(m.live.time)})` : "live"} right={m.name} footer={medians(m.live, m.run)} />
          <p className="mt-1 text-xs text-muted">Switching models is a setting (Settings page), not a promotion.</p>
        </Card>
      ))}
      {data.shadows.length + data.prompts.length + data.models.length === 0 && <p className="text-sm text-muted">Nothing to compare yet.</p>}
    </div>
  );
}

type Row = [string, number | null | undefined, number | null | undefined];

function sides(a: PromptEvalSide, b: PromptEvalSide): Row[] {
  return [
    ["Answerable questions answered", ratio(a.answered, a.answerable), ratio(b.answered, b.answerable)],
    ["Sentences supported", ratio(a.supported_sentences, a.sentences), ratio(b.supported_sentences, b.sentences)],
    ["Trap questions refused", ratio(a.refused_traps, a.traps), ratio(b.refused_traps, b.traps)],
  ];
}

function medians(a: EvalRun | null, b: EvalRun): string {
  return `median seconds per answer: ${a?.median_seconds ?? "–"} → ${b.median_seconds ?? "–"}`;
}

function Side({ rows, left, right, footer }: { rows: Row[]; left: string; right: string; footer?: string }) {
  return (
    <table className="w-full text-left text-xs">
      <thead className="text-muted"><tr><th className="py-1">Measure</th><th>{left}</th><th>{right}</th><th>Change</th></tr></thead>
      <tbody>
        {rows.map(([label, a, b]) => {
          const d = a != null && b != null ? b - a : null;
          return (
            <tr key={label} className="border-t border-line">
              <td className="py-1">{label}</td>
              <td className="tabular-nums">{pct(a)}</td>
              <td className="tabular-nums">{pct(b)}</td>
              <td className="tabular-nums">
                {d == null ? "–" : Math.abs(d) < 0.005 ? "same" : `${d > 0 ? "▲ +" : "▼ "}${Math.round(d * 100)} pts`}
              </td>
            </tr>
          );
        })}
      </tbody>
      {footer && <tfoot><tr><td colSpan={4} className="pt-1 text-muted">{footer}</td></tr></tfoot>}
    </table>
  );
}

function Card({ title, status, children }: { title: string; status: string; children: React.ReactNode }) {
  return (
    <article className="rounded-xl border border-line bg-surface p-4 text-sm">
      <header className="mb-2 flex items-baseline gap-2"><h3 className="font-semibold">{title}</h3><span className="text-xs text-muted">{status}</span></header>
      {children}
    </article>
  );
}

function Btn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return <button className="rounded-md border border-line px-2 py-1" onClick={onClick}>{children}</button>;
}
