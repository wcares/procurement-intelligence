"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { EvaluationResponse } from "@/lib/api/types";
import { hasRole, useAuth } from "@/components/auth";
import { Button } from "@/components/ui/button";
import { ComparisonsView } from "./comparisons";
import { FeedbackReview } from "./feedback-review";
import { Labelling } from "./labelling";
import { ModelsView } from "./models-view";
import { QualityChart } from "./quality-chart";
import { RunsTable } from "./runs-table";

// Hidden 2026-10-28, not removed: the queue for labelling evaluation data is a tool for the people who maintain the
// evaluation set. Set to true to bring it back.
const SHOW_LABELLING = false;

export function EvaluationView() {
  const [data, setData] = useState<EvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const { user } = useAuth();
  const admin = hasRole(user?.role, "admin");   // reviewers label and read; runs, promotions and prompts are admin
  const load = useCallback(() => api.evaluation().then(setData).catch((e) => setError((e as Error).message)), []);
  useEffect(() => {
    load();
  }, [load]);

  async function run(answers: boolean) {
    try {
      const r = await api.runEvaluation(answers);
      setNote(r.queued ? `${answers ? "Full evaluation" : "Search-quality evaluation"} queued: it runs in the background when the app is idle${answers ? " (about 10 minutes)" : ""}.` : r.note);
    } catch (e) {
      setNote((e as Error).message);
    }
  }

  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!data) return <p className="text-sm text-ink-muted">Loading…</p>;
  return (
    <div className="space-y-10">
      <Section title="Quality over time" action={admin &&
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Button variant="outline" size="xs" className="border-line" onClick={() => run(false)}>Run search-quality check</Button>
          <Button variant="outline" size="xs" className="border-line" onClick={() => run(true)}>Run full evaluation</Button>
          {note && <span className="text-ink-muted">{note}</span>}
        </div>
      }>
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
      <FeedbackReview />
    </div>
  );
}

function Section({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
