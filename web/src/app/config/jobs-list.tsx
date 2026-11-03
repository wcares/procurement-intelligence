"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Job, JobsResponse } from "@/lib/api/types";
import { jobLabel, jobState, unfinishedFirst } from "@/components/job-status";

const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** The work the app does in the background, newest first: what it is, why it ran, and how it went. */
export function JobsList() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [queue, setQueue] = useState<JobsResponse | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const act = (p: Promise<JobsResponse>) => p.then((r) => { setJobs(unfinishedFirst(r.jobs)); setQueue(r); setNote(null); }).catch((e: Error) => setNote(e.message));
  useEffect(() => {
    const load = () => api.jobs().then((r) => { setJobs(unfinishedFirst(r.jobs)); setQueue(r); }).catch(() => setJobs([]));
    void load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);
  return (
    <section>
      <h3 className="font-semibold">Recent jobs</h3>
      <p className="mt-1 mb-4 text-sm text-ink-muted">
        Work the app does on its own: checking the World Bank sources, updating the data, measuring quality, retraining
        the forecast.{" "}
        {queue?.waitsForModels
          ? <>A job waits only while a user&apos;s request is using a model it needs, and starts {queue.runAfterIdleSeconds} s
            after that model is free; a user needing the model pauses it after its current step. Light jobs (checking
            sources, taking in documents and records) never wait. Pause a job, or start it later, from its row.</>
          : <>Light jobs start at once; heavier ones wait until the app has had no requests for {queue?.runAfterIdleSeconds ?? 5} s.</>}{" "}
        Updates every 10 seconds.
      </p>
      {note && <p className="mb-2 text-sm text-risk-high">{note}</p>}
      {jobs === null ? <p className="text-sm text-ink-muted">Loading…</p> : jobs.length === 0 ? <p className="text-sm text-ink-muted">No jobs yet.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs text-ink-muted">
              <tr><th className="py-2 pr-4 font-normal">Job</th><th className="py-2 pr-4 font-normal">Why</th><th className="py-2 pr-4 font-normal">Started</th><th className="py-2 font-normal">State</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {jobs.map((j) => {
                const s = jobState(j, queue);
                return (
                  <tr key={j.id} className="align-top">
                    <td className="py-2 pr-4">{jobLabel(j.kind)}</td>
                    <td className="py-2 pr-4 text-ink-muted">{j.reason}</td>
                    <td className="py-2 pr-4 whitespace-nowrap text-ink-muted">{when(j.started_at ?? j.created_at)}</td>
                    <td className={`py-2 ${s.tone === "bad" ? "text-risk-high" : s.tone === "ok" ? "text-risk-low" : "text-ink-muted"}`}>
                      {s.text}
                      {(j.status === "pending" || j.status === "running") && (
                        <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                          {j.hold || (j.not_before && new Date(`${j.not_before}Z`) > new Date())
                            ? <button type="button" className="rounded border border-line px-2 py-0.5" onClick={() => void act(api.resumeJob(j.id))}>{j.hold ? "Resume" : "Run now"}</button>
                            : <button type="button" className="rounded border border-line px-2 py-0.5" onClick={() => void act(api.pauseJob(j.id))}>Pause</button>}
                          <select aria-label={`Run ${jobLabel(j.kind)} later`} className="rounded border border-line bg-surface px-1 py-0.5" value=""
                            onChange={(e) => e.target.value && void act(api.laterJob(j.id, e.target.value as "30m"))}>
                            <option value="">Run later…</option>
                            <option value="30m">in 30 minutes</option>
                            <option value="1h">in 1 hour</option>
                            <option value="2h">in 2 hours</option>
                            <option value="4h">in 4 hours</option>
                            <option value="tonight">tonight (22:00)</option>
                          </select>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
