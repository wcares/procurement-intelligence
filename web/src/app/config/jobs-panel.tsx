"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Job, JobsResponse } from "@/lib/api/types";

const JOB_LABELS: Record<string, string> = {
  drift_check: "Prediction drift check",
  retrain: "Retrain prediction models",
  refresh: "Refresh World Bank data",
  feedback_review: "Review user feedback",
};

function jobSummary(j: Job): string {
  if (j.status === "failed" || (j.status === "pending" && j.error)) return `error: ${j.error}`;
  const r = j.result;
  if (!r) return j.reason;
  if (typeof r.why === "string") return r.why;
  if (typeof r.n === "number") return `trained on ${r.n} packages${r.reloaded ? ", backend reloaded" : ""}`;
  if (r.items && typeof r.items === "object") {
    const c = r.items as Record<string, number>;
    return `${c.flagged_citation ?? 0} flagged citations, ${c.refused_question ?? 0} refused questions, ${c.not_useful ?? 0} not useful; ${r.demoted} demoted`;
  }
  return r.reloaded ? "done, backend reloaded" : "done";
}

export function Jobs() {
  const [data, setData] = useState<JobsResponse | null>(null);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () => api.jobs().then((r) => live && setData(r)).catch(() => live && setData(null));
    load();
    const t = setInterval(load, 10000); // GET /jobs does not count as activity, so polling does not delay jobs
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  async function queue(kind: string) {
    try {
      const r = await api.queueJob(kind);
      setNote(r.queued ? `${JOB_LABELS[kind]} queued; it runs after ${data?.runAfterIdleSeconds ?? 300} s without requests.` : r.note);
      setData(await api.jobs());
    } catch (e) {
      setNote((e as Error).message);
    }
  }

  if (!data) return null;
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Background jobs</h2>
      <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
        <p className="text-xs text-muted">
          Jobs run only after {data.runAfterIdleSeconds} s without requests and pause when someone uses the app. Idle now:{" "}
          {data.idleSeconds} s{data.running ? ` · running: ${JOB_LABELS[data.running] ?? data.running}` : ""}
          {!data.workerOn && " · worker is off (PROCINTEL_JOBS=0)"}
          {data.workerMode === "external" && " · separate worker processes"}. High-priority jobs run first, background
          jobs only when nothing else waits; a running job pauses between steps when a more urgent one arrives.
        </p>
        <div className="flex flex-wrap gap-2">
          {Object.entries(JOB_LABELS).map(([kind, label]) => (
            <button key={kind} className="rounded-md border border-line px-2 py-1 text-xs" onClick={() => queue(kind)}>
              Queue: {label}
            </button>
          ))}
        </div>
        {note && <p className="text-xs text-muted">{note}</p>}
        {data.jobs.length === 0 ? (
          <p className="text-sm text-muted">No jobs yet.</p>
        ) : (
          <ul className="divide-y divide-line text-sm">
            {data.jobs.slice(0, 10).map((j) => (
              <li key={j.id} className="flex flex-wrap items-baseline gap-x-2 py-1.5">
                <span className="font-medium">{JOB_LABELS[j.kind] ?? j.kind}</span>
                <span className={`text-xs ${j.status === "failed" ? "text-risk-high" : "text-muted"}`}>{j.status}</span>
                {j.priority !== "normal" && <span className="rounded border border-line px-1 text-xs text-muted">{j.priority}</span>}
                <span className="text-xs text-muted">{new Date(j.finished_at ?? j.created_at).toLocaleString()}</span>
                <span className="w-full text-xs text-muted">{jobSummary(j)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
