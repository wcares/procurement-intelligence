"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { StatusCounts, StatusRules } from "@/lib/api/types";

const OVERRIDES: Record<string, string> = { closed: "project status Closed", closing_passed: "closing date passed",
  completion_report: "completion report published" };

/** The parameters that stamp every package active, finished, replaced or stale (procintel.monitoring.status), with a
 * dry run of how many packages a change moves before it is saved. */
export function StatusRulesView() {
  const [data, setData] = useState<{ rules: StatusRules; defaults: StatusRules; customised: boolean; counts: StatusCounts } | null>(null);
  const [draft, setDraft] = useState<StatusRules | null>(null);
  const [dry, setDry] = useState<{ moves: { from: string; to: string; packages: number }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.statusRules().then((d) => (setData(d), setDraft(d.rules))).catch((e) => setError((e as Error).message));
  }, []);
  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!data || !draft) return <p className="text-sm text-ink-muted">Loading…</p>;
  const c = data.counts;
  const run = (f: () => Promise<unknown>) => f().catch((e) => setError((e as Error).message));
  const save = (r: StatusRules) => run(async () => { const d = await api.saveStatusRules(r); setData(d); setDraft(d.rules); setDry(null); });
  const field = "w-24 rounded border border-line bg-surface px-1 py-0.5";
  return (
    <div className="space-y-4 text-sm">
      <p className="text-ink-muted">
        Now: {c.status.active} active ({c.phase.bidding ?? 0} in bidding, {c.phase.contract ?? 0} contract running),{" "}
        {c.status.finished} finished, {c.status.replaced} replaced, {c.status.stale} stale{data.customised ? " (edited rules)" : " (default rules)"}.
        Checked in order: replaced, contract ended, project ended, contract running, too old without an award, else in bidding.
      </p>
      <div className="grid gap-3 rounded-xl border border-line bg-surface p-4 text-xs sm:grid-cols-2">
        <label className="space-y-1"><span className="block font-medium">Stale after (share of comparable tenders)</span>
          <input type="number" step={0.01} min={0.5} max={0.99} className={field} value={draft.stale_quantile}
            onChange={(e) => setDraft({ ...draft, stale_quantile: Number(e.target.value) })} />
          <span className="block text-ink-muted">no award and open longer than this share of comparable awarded tenders took</span></label>
        <label className="space-y-1"><span className="block font-medium">... or after (days)</span>
          <input type="number" min={30} className={field} value={draft.stale_max_days ?? ""}
            onChange={(e) => setDraft({ ...draft, stale_max_days: e.target.value ? Number(e.target.value) : null })} />
          <span className="block text-ink-muted">empty: no fixed cap</span></label>
        <label className="space-y-1"><span className="block font-medium">Contract end margin (days)</span>
          <input type="number" min={0} className={field} value={draft.contract_end_margin}
            onChange={(e) => setDraft({ ...draft, contract_end_margin: Number(e.target.value) })} /></label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={draft.estimate_contract_end}
          onChange={(e) => setDraft({ ...draft, estimate_contract_end: e.target.checked })} />
          estimate a contract&apos;s end from comparable contracts when its duration is not stated</label>
        <div className="space-y-1 sm:col-span-2"><span className="block font-medium">A project counts as ended when</span>
          {Object.entries(OVERRIDES).map(([k, label]) => (
            <label key={k} className="mr-4 inline-flex items-center gap-1">
              <input type="checkbox" checked={draft.project_overrides.includes(k)} onChange={(e) => setDraft({ ...draft,
                project_overrides: e.target.checked ? [...draft.project_overrides, k] : draft.project_overrides.filter((x) => x !== k) })} />
              {label}
            </label>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button className="rounded-md border border-line px-3 py-1.5" onClick={() => run(async () => setDry(await api.statusDryRun(draft)))}>Dry run</button>
        <button className="rounded-md bg-brand px-3 py-1.5 text-white" onClick={() => save(draft)}>Save</button>
        {data.customised && <button className="underline" onClick={() => save(data.defaults)}>reset to defaults</button>}
      </div>
      {dry && (
        <p className="text-xs">
          {dry.moves.length === 0 ? "No package would change status." :
            dry.moves.map((m) => `${m.packages} from ${m.from} to ${m.to}`).join(" · ")}
        </p>
      )}
    </div>
  );
}
