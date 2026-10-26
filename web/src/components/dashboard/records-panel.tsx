"use client";

import type { DashRecords } from "@/lib/api/types";

/** The records behind a selected ranking row or heat-map cell. */
export function RecordsPanel({ title, data, onClose }: { title: string; data: DashRecords | null; onClose: () => void }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="font-semibold">{title}</h3>
        <button className="text-xs underline" onClick={onClose}>close</button>
      </div>
      {!data ? (
        <p className="text-sm text-ink-muted">Loading…</p>
      ) : data.records.length === 0 ? (
        <p className="text-sm text-ink-muted">No records with this measure.</p>
      ) : data.kind === "packages" ? (
        <ul className="max-h-80 divide-y divide-line overflow-auto text-sm">
          {data.records.map((r) => (
            <li key={r.packageId} className="flex flex-wrap gap-x-3 py-1.5">
              <span className="w-20 font-medium tabular-nums">{r.days} days</span>
              <span className="min-w-0 flex-1">{r.description || r.packageId}</span>
              <a className="text-xs text-ink-muted underline" href={r.url} target="_blank" rel="noreferrer">{r.projectId} · {r.method}</a>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="max-h-80 divide-y divide-line overflow-auto text-sm">
          {data.records.map((r) => (
            <li key={r.projectId} className="py-1.5">
              <a className="font-medium underline" href={r.url} target="_blank" rel="noreferrer">{r.name}</a>
              <span className="text-xs text-ink-muted">
                {" "}· {r.projectId}
                {r.rebid && " · re-tendering"}
                {r.amendment && " · amendments"}
                {r.procurementBelowSatisfactory && " · procurement rated below satisfactory"}
                {r.problemPassages != null && ` · ${r.problemPassages} problem passages`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
