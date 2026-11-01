"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Job } from "@/lib/api/types";

/** What a background job is, in plain words. */
export const JOB_LABEL: Record<string, string> = {
  evaluate: "Measure quality",
  detect_changes: "Check the sources for changes",
  pipeline_batch: "Update the data after a change",
  pipeline_batch_light: "Take in new documents",
  drift_check: "Check whether the forecast model needs retraining",
  retrain: "Retrain the forecast model",
  refresh: "Weekly full refresh of the data",
  feedback_review: "Review user feedback",
  retention: "Delete old logs",
  prompt_evaluate: "Test a changed prompt",
  shadow_evaluate: "Test an alternative setup",
  shadow_build: "Build an alternative setup",
  shadow_promote: "Switch to an alternative setup",
};
export const jobLabel = (kind: string) => JOB_LABEL[kind] ?? kind.replace(/_/g, " ");

const mins = (from: string, to?: string | null) => {
  const m = Math.round(((to ? new Date(to) : new Date()).getTime() - new Date(from).getTime()) / 60000);
  return m < 1 ? "under a minute" : `${m} min`;
};

/** One line: where a job is (waiting, running, done, failed) and, when done or failed, how long it took or why. */
export function jobState(j: Job): { text: string; tone: "muted" | "ok" | "bad" } {
  if (j.status === "pending") return { text: "Waiting: it starts when nobody is using the app", tone: "muted" };
  if (j.status === "running") return { text: `Running for ${mins(j.started_at ?? j.created_at)}`, tone: "muted" };
  if (j.status === "done") return { text: `Done in ${mins(j.started_at ?? j.created_at, j.finished_at)}`, tone: "ok" };
  return { text: `Failed: ${j.error ?? "no reason given"}`, tone: "bad" };
}

/** The live state of one job (checked every 5 seconds until it is done or failed); onDone runs once when it finishes. */
export function JobStatus({ id, onDone }: { id: string; onDone?: () => void }) {
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    let live = true;
    const check = () => api.jobs().then((r) => {
      if (!live) return;
      const j = r.jobs.find((x) => x.id === id) ?? null;
      setJob(j);
      if (j && (j.status === "done" || j.status === "failed")) {
        clearInterval(t);
        if (j.status === "done") onDone?.();
      }
    }).catch(() => null);
    const t = setInterval(check, 5000);
    void check();
    return () => { live = false; clearInterval(t); };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!job) return <span className="text-ink-muted">Queued.</span>;
  const s = jobState(job);
  return <span className={s.tone === "bad" ? "text-risk-high" : s.tone === "ok" ? "text-risk-low" : "text-ink-muted"}>{jobLabel(job.kind)}: {s.text}.</span>;
}
