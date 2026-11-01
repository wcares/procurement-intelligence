"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { EvaluationResponse } from "@/lib/api/types";
import { hasRole, useAuth } from "@/components/auth";
import { Button } from "@/components/ui/button";
import { QualitySummary } from "./quality-summary";
import { JobStatus } from "@/components/job-status";

export function EvaluationView() {
  const [data, setData] = useState<EvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const { user } = useAuth();
  const admin = hasRole(user?.role, "admin");   // reviewers label and read; runs, promotions and prompts are admin
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
    </div>
  );
}
