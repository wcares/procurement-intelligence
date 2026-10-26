"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { PipelineResponse } from "@/lib/api/types";
import { RulesEditor } from "./rules-editor";

/** The rules: which events lead to which actions, with the editor (validation, dry run on the last days' events,
 * reset to the defaults). */
export function RulesView() {
  const [data, setData] = useState<PipelineResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.pipeline().then(setData).catch((e) => setError((e as Error).message));
  }, []);
  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!data) return <p className="text-sm text-ink-muted">Loading…</p>;
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-muted">
        {data.rules.length} rules{data.customised ? ", edited (saved in the data folder)" : ", the defaults"}. A rule
        runs its actions when one of its events arrives; an action asked for by many events runs once per batch, in the
        data&apos;s order.
      </p>
      <ul className="space-y-1 rounded-xl border border-line bg-surface p-4 text-xs">
        {data.rules.map((r) => (
          <li key={r.id} className={r.enabled ? "" : "text-ink-muted line-through"}>
            <span className="font-medium">{r.id}</span>: <span className="font-mono">{r.on.join(", ")}</span>
            {r.fields.length > 0 && <span className="text-ink-muted"> (fields: {r.fields.join(", ")})</span>} → {r.do.join(", ")}
          </li>
        ))}
      </ul>
      <div className="rounded-xl border border-line bg-surface p-4">
        <h2 className="mb-2 text-sm font-semibold">Edit</h2>
        <RulesEditor data={data} onSaved={setData} />
      </div>
    </div>
  );
}
