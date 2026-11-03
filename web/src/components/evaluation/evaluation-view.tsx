"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { EvaluationResponse } from "@/lib/api/types";
import { hasRole, useAuth } from "@/components/auth";
import { Button } from "@/components/ui/button";
import { JobStatus } from "@/components/job-status";
import { ComparisonsView } from "./comparisons";
import { Labelling } from "./labelling";
import { ModelsView } from "./models-view";
import { QualityChart } from "./quality-chart";
import { QualitySummary } from "./quality-summary";
import { RunsTable } from "./runs-table";

// Hidden 2026-10-28, not removed: the queue for labelling evaluation data is a tool for the people who maintain the
// evaluation set. Set to true to bring it back.
const SHOW_LABELLING = false;

export function EvaluationView() {
  const [data, setData] = useState<EvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const { user } = useAuth();
  const admin = hasRole(user?.role, "admin");   // the page is admin-only; kept for a read-only role later
  const load = useCallback(() => api.evaluation().then(setData).catch((e) => setError((e as Error).message)), []);
  useEffect(() => {
    load();
  }, [load]);

  async function run(answers: boolean) {
    try {
      const r = await api.runEvaluation(answers);
      if (r.queued) { setJobId(r.queued); setNote(null); return; }
      // one is already waiting or running: follow that one
      const waiting = (await api.jobs()).jobs.find((j) => j.kind === "evaluate" && (j.status === "pending" || j.status === "running"));
      setJobId(waiting?.id ?? null); setNote(waiting ? null : r.note);
    } catch (e) {
      setNote((e as Error).message);
    }
  }

  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!data) return <p className="text-sm text-ink-muted">Loading…</p>;
  return (
    <div className="space-y-10">
      <QualitySummary data={data} />
      {admin && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Button variant="outline" size="sm" className="border-line" onClick={() => run(false)}>Measure search again</Button>
          <Button variant="outline" size="sm" className="border-line" onClick={() => run(true)}>Measure everything again (about 10 minutes)</Button>
          {jobId && <JobStatus key={jobId} id={jobId} onDone={load} />}
          {note && <span className="text-ink-muted">{note}</span>}
        </div>
      )}
      {/* Closed by default; feedback to review is in Settings. */}
      <details className="border-t border-line pt-6">
        <summary className="cursor-pointer text-sm text-ink-muted">Details for engineers: every run, experiments, model retrains</summary>
        <div className="mt-6 space-y-10">
          <Section title="Quality over time">
            <p className="mb-2 text-xs text-ink-muted">
              Each run scores the evaluation questions (eval/questions.jsonl): search against judged passages, answers for
              support by their cited passages, and trap questions that must be refused. Dashed lines: a change made between
              runs (hover a run to see which).
            </p>
            <QualityChart runs={data.quality} />
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-ink-muted">Every run as a table ({data.quality.length})</summary>
              <div className="mt-2"><RunsTable runs={data.quality} /></div>
            </details>
          </Section>
          <Section title="Comparisons"><ComparisonsView data={data.comparisons} onChanged={load} /></Section>
          <Section title="Prediction model"><ModelsView data={data.models} /></Section>
          {SHOW_LABELLING && <Section title="Labelling queue"><Labelling /></Section>}
        </div>
      </details>
    </div>
  );
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
