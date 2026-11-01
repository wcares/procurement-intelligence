"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { MonitoredProject } from "@/lib/api/types";
import { ProjectMap } from "./project-map";
import { ProjectMediaPanel } from "./project-media";
import { StatusBadge } from "./status-badge";

/** Ongoing projects (the ones you follow, or all with active packages) and, opened, their packages with status and
 * forecast; warnings first. */
export function OngoingWork({ openProject }: { openProject?: string | null }) {
  const [scope, setScope] = useState<"watched" | "ongoing">("ongoing");
  const [projects, setProjects] = useState<MonitoredProject[] | null>(null);
  const [open, setOpen] = useState<string | null>(openProject ?? null);
  const [detail, setDetail] = useState<Record<string, MonitoredProject>>({});
  useEffect(() => {
    api.monitoredProjects(scope).then((r) => setProjects(r.projects)).catch(() => setProjects([]));
  }, [scope]);
  useEffect(() => {
    if (open && !detail[open]) api.monitoredProject(open).then((p) => setDetail((d) => ({ ...d, [open]: p }))).catch(() => null);
  }, [open, detail]);

  return (
    <div className="space-y-3">
      <div className="flex gap-5 border-b border-line text-sm">
        {(["ongoing", "watched"] as const).map((s) => (
          <button key={s} onClick={() => (setProjects(null), setScope(s))}
            className={`-mb-px border-b-2 pb-2 ${scope === s ? "border-brand-2 font-semibold text-brand-strong" : "border-transparent text-ink-muted hover:text-foreground"}`}>
            {s === "ongoing" ? "all ongoing projects" : "projects on my watch-list"}
          </button>
        ))}
      </div>
      <ProjectMap scope={scope} focus={open} onOpen={(id) => setOpen(id)} />
      {projects === null ? <p className="text-xs text-ink-muted">Loading…</p> : projects.length === 0 ? (
        <p className="text-xs text-ink-muted">{scope === "watched" ? "No project on your watch-list yet: add project ids below." : "No ongoing projects."}</p>
      ) : (
        <ul className="divide-y divide-line border-y border-line">
          {projects.map((p) => (
            <li key={p.projectId} className="px-3 py-2 text-sm">
              <button className="flex w-full flex-wrap items-baseline gap-x-3 text-left" onClick={() => setOpen(open === p.projectId ? null : p.projectId)}>
                <span className="font-medium">{p.name}</span>
                <span className="text-xs text-ink-muted">{p.projectId} · {p.countryCode}{p.closingDate ? ` · closes ${p.closingDate.slice(0, 10)}` : ""}</span>
                <span className="ml-auto text-xs">
                  {p.packages.active} active ({p.bidding} in bidding) · {p.packages.finished} finished · {p.packages.stale} stale
                  {p.packagesWithWarnings ? <span className="ml-2 text-risk-medium">⚠ {p.packagesWithWarnings} with warnings</span> : null}
                </span>
              </button>
              {p.isr?.downgrades.length ? <p className="text-xs text-risk-medium">Newest ISR ({p.isr.date}) downgraded: {p.isr.downgrades.join("; ")}</p> : null}
              {open === p.projectId && (
                detail[p.projectId]?.packageList ? (
                  <ul className="mt-2 space-y-1 border-l border-line pl-3 text-xs">
                    {detail[p.projectId].packageList!.filter((k) => k.status !== "finished").slice(0, 40).map((k) => (
                      <li key={k.packageId} className="flex flex-wrap items-baseline gap-x-2">
                        <StatusBadge status={k.status} phase={k.phase} />
                        <Link href={`/package?id=${encodeURIComponent(k.packageId)}`} className="underline">{k.description.slice(0, 80)}</Link>
                        <span className="text-ink-muted">{k.methodCode}{k.ageDays != null && k.phase === "bidding" ? ` · open ${k.ageDays} days` : ""}</span>
                        {k.forecast?.award && <span>award ~{k.forecast.award.date}</span>}
                        {k.forecast?.warnings.map((w) => <span key={w.kind} className="text-risk-medium" title={w.text}>⚠ {w.kind.replace("_", " ")}</span>)}
                      </li>
                    ))}
                    <li className="text-ink-muted">{detail[p.projectId].packages.finished} finished packages not listed.</li>
                  </ul>
                ) : <p className="mt-1 text-xs text-ink-muted">Loading packages…</p>
              )}
              {open === p.projectId && (
                <ProjectMediaPanel projectId={p.projectId}
                  packages={(detail[p.projectId]?.packageList ?? []).filter((k) => k.status !== "finished").slice(0, 40)
                    .map((k) => ({ id: k.packageId, label: `${k.packageId} · ${k.description.slice(0, 40)}` }))} />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
