"use client";

import { useState } from "react";
import { api } from "@/lib/api/client";
import type { DryRunResponse, PipelineResponse, PipelineRule } from "@/lib/api/types";

const box = "rounded-md border border-line bg-surface px-2 py-1 text-xs";

/** Edit the pipeline rules: events and an optional field condition -> actions, from the registered lists only. */
export function RulesEditor({ data, onSaved }: { data: PipelineResponse; onSaved: (d: PipelineResponse) => void }) {
  const [rules, setRules] = useState<PipelineRule[]>(data.rules);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [dry, setDry] = useState<DryRunResponse | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const label = (name: string) => data.actions.find((a) => a.name === name)?.label ?? name;

  const update = (i: number, patch: Partial<PipelineRule>) => {
    setRules(rules.map((r, j) => (j === i ? { ...r, ...patch } : r)));
    setDry(null);
  };
  const toggle = (list: string[], v: string) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  async function dryRun() {
    const r = await api.dryRunRules(rules);
    if ("errors" in r) return setErrors(r.errors);
    setErrors({});
    setDry(r);
  }

  async function save() {
    const r = await api.saveRules(rules);
    if ("errors" in r) return setErrors(r.errors);
    setErrors({});
    setMsg("Rules saved; the next detection uses them.");
    onSaved(r);
  }

  async function reset() {
    const r = await api.resetRules();
    setRules(r.rules);
    setDry(null);
    setErrors({});
    setMsg("Default rules restored.");
    onSaved(r);
  }

  return (
    <div className="space-y-2 text-xs">
      <p className="text-ink-muted">
        {data.customised ? "Edited rules in use." : "Default rules in use."} Run a dry run to see what the rules would
        have done on the last week&apos;s changes before saving.
      </p>
      {errors["(set)"] && <p className="text-risk-high">{errors["(set)"]}</p>}
      <ul className="space-y-2">
        {rules.map((r, i) => (
          <li key={i} className="space-y-1 rounded-md border border-line p-2">
            <div className="flex flex-wrap items-center gap-2">
              <input className={`${box} w-48 font-mono`} value={r.id} onChange={(e) => update(i, { id: e.target.value })} aria-label="Rule id" />
              <label className="flex items-center gap-1">
                <input type="checkbox" checked={r.enabled} onChange={(e) => update(i, { enabled: e.target.checked })} /> enabled
              </label>
              <button className="ml-auto underline" onClick={() => (setRules(rules.filter((_, j) => j !== i)), setDry(null))}>remove</button>
            </div>
            <div>
              <span className="text-ink-muted">when </span>
              {data.eventTypes.map((e) => (
                <label key={e} className="mr-2 inline-flex items-center gap-0.5 font-mono">
                  <input type="checkbox" checked={r.on.includes(e)} onChange={() => update(i, { on: toggle(r.on, e) })} />
                  {e}
                </label>
              ))}
            </div>
            <div className="flex items-center gap-1">
              <span className="text-ink-muted">only if these fields changed (optional):</span>
              <input className={`${box} flex-1`} value={r.fields.join(", ")} placeholder="e.g. status, closing_date"
                onChange={(e) => update(i, { fields: e.target.value.split(",").map((f) => f.trim()).filter(Boolean) })} />
            </div>
            <div>
              <span className="text-ink-muted">do </span>
              {data.actions.map((a) => (
                <label key={a.name} className="mr-2 inline-flex items-center gap-0.5" title={a.label}>
                  <input type="checkbox" checked={r.do.includes(a.name)} onChange={() => update(i, { do: toggle(r.do, a.name) })} />
                  {a.name}
                </label>
              ))}
            </div>
            {errors[r.id || "(new rule)"] && <p className="text-risk-high">{errors[r.id || "(new rule)"]}</p>}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <button className={box} onClick={() => setRules([...rules, { id: `rule-${rules.length + 1}`, on: [], fields: [], do: [], enabled: true }])}>Add rule</button>
        <button className={box} onClick={dryRun}>Dry run</button>
        <button className={box} onClick={save}>Save</button>
        <button className={box} onClick={reset}>Reset to defaults</button>
      </div>
      {msg && <p className="text-ink-muted">{msg}</p>}
      {dry && (
        <div className="rounded-md border border-line p-2">
          <p>
            Last {dry.days} days: {dry.candidate.events} changes in {dry.candidate.batches} detection runs.
          </p>
          <table className="w-full text-left">
            <thead className="text-ink-muted"><tr><th>Action</th><th>Edited: runs (changes)</th><th>Current: runs (changes)</th></tr></thead>
            <tbody>
              {Array.from(new Set([...Object.keys(dry.candidate.actions), ...Object.keys(dry.current.actions)])).map((a) => (
                <tr key={a} className="border-t border-line" title={label(a)}>
                  <td className="font-mono">{a}</td>
                  <td>{dry.candidate.actions[a] ? `${dry.candidate.actions[a].runs} (${dry.candidate.actions[a].events})` : "–"}</td>
                  <td>{dry.current.actions[a] ? `${dry.current.actions[a].runs} (${dry.current.actions[a].events})` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
