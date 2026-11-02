"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Job, JobsResponse } from "@/lib/api/types";

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

/** One line: where a job is (waiting, running, done, failed) and, when done or failed, how long it took or why. With the
 * queue's state it says why a waiting job waits: a light one starts within seconds; a heavier one waits until the app
 * has had no requests for a while, and how long is left. */
/** Running and waiting jobs first (newest first within each), so an unfinished job is never hidden under finished ones. */
export const unfinishedFirst = (jobs: Job[]) => {
  const rank = (j: Job) => (j.status === "running" ? 0 : j.status === "pending" ? 1 : 2);
  return jobs.map((j, i) => [j, i] as const).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(([j]) => j);
};

type Queue = Pick<JobsResponse, "idleSeconds" | "runAfterIdleSeconds" | "lightKinds" | "dedicatedModel" | "waitsForModels" | "modelsFreeSeconds">;

const clockTime = (utc: string) => new Date(utc.endsWith("Z") ? utc : `${utc}Z`).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

export function jobState(j: Job, q?: Queue | null): { text: string; tone: "muted" | "ok" | "bad" } {
  if (j.status === "pending") {
    if (j.hold) return { text: "Paused: starts when you resume it", tone: "muted" };
    if (j.not_before && new Date(`${j.not_before}Z`) > new Date()) return { text: `Scheduled: starts after ${clockTime(j.not_before)}`, tone: "muted" };
    if (!q) return { text: "Waiting to start", tone: "muted" };
    if (q.lightKinds?.includes(j.kind)) return { text: "Starting within seconds", tone: "muted" };
    if (q.waitsForModels) {
      const free = q.modelsFreeSeconds;
      if (free === null || free === undefined || free >= q.runAfterIdleSeconds) return { text: "Starting within seconds", tone: "muted" };
      return { text: `Waiting: a user is using the model it needs; starts ${q.runAfterIdleSeconds} s after it is free`, tone: "muted" };
    }
    if (q.dedicatedModel || q.idleSeconds >= q.runAfterIdleSeconds) return { text: "Starting within seconds", tone: "muted" };
    return { text: `Waiting for a quiet moment: starts after ${q.runAfterIdleSeconds - q.idleSeconds} more s without requests`, tone: "muted" };
  }
  if (j.status === "running" && j.stop) return { text: "Pausing after its current step", tone: "muted" };
  if (j.status === "running") return { text: `Running for ${mins(j.started_at ?? j.created_at)}`, tone: "muted" };
  if (j.status === "done") return { text: `Done in ${mins(j.started_at ?? j.created_at, j.finished_at)}`, tone: "ok" };
  return { text: `Failed: ${j.error ?? "no reason given"}`, tone: "bad" };
}

/** The live state of one job (checked every 5 seconds until it is done or failed); onDone runs once when it finishes. */
export function JobStatus({ id, onDone }: { id: string; onDone?: () => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [queue, setQueue] = useState<JobsResponse | null>(null);
  useEffect(() => {
    let live = true;
    const check = () => api.jobs().then((r) => {
      if (!live) return;
      const j = r.jobs.find((x) => x.id === id) ?? null;
      setJob(j);
      setQueue(r);
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
  const s = jobState(job, queue);
  return <span className={s.tone === "bad" ? "text-risk-high" : s.tone === "ok" ? "text-risk-low" : "text-ink-muted"}>{jobLabel(job.kind)}: {s.text}.</span>;
}
