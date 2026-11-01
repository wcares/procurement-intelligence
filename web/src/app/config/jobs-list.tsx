"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Job } from "@/lib/api/types";
import { jobLabel, jobState } from "@/components/job-status";

const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** The work the app does in the background, newest first: what it is, why it ran, and how it went. */
export function JobsList() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  useEffect(() => {
    const load = () => api.jobs().then((r) => setJobs(r.jobs)).catch(() => setJobs([]));
    void load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);
  return (
    <section>
      <h2 className="text-xl font-semibold">Background jobs</h2>
      <p className="mt-1 mb-4 text-sm text-ink-muted">
        Work the app does on its own: checking the World Bank sources, updating the data, measuring quality, retraining
        the forecast. A job waits until nobody is using the app, so it never slows anyone down. Updates every 10 seconds.
      </p>
      {jobs === null ? <p className="text-sm text-ink-muted">Loading…</p> : jobs.length === 0 ? <p className="text-sm text-ink-muted">No jobs yet.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs text-ink-muted">
              <tr><th className="py-2 pr-4 font-normal">Job</th><th className="py-2 pr-4 font-normal">Why</th><th className="py-2 pr-4 font-normal">Started</th><th className="py-2 font-normal">State</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {jobs.map((j) => {
                const s = jobState(j);
                return (
                  <tr key={j.id} className="align-top">
                    <td className="py-2 pr-4">{jobLabel(j.kind)}</td>
                    <td className="py-2 pr-4 text-ink-muted">{j.reason}</td>
                    <td className="py-2 pr-4 whitespace-nowrap text-ink-muted">{when(j.started_at ?? j.created_at)}</td>
                    <td className={`py-2 ${s.tone === "bad" ? "text-risk-high" : s.tone === "ok" ? "text-risk-low" : "text-ink-muted"}`}>{s.text}</td>
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
