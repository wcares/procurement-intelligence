"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Options, WatchKind, WatchList } from "@/lib/api/types";

const EMPTY: WatchList = { country: [], sector: [], proc_group: [], method: [], project: [] };

/** What the planner follows. Alerts appear when the pipeline records changes inside this scope. */
export function WatchListEditor({ onSaved }: { onSaved?: () => void }) {
  const [opts, setOpts] = useState<Options | null>(null);
  const [watch, setWatch] = useState<WatchList>(EMPTY);
  const [project, setProject] = useState("");
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    api.options().then(setOpts).catch(() => setOpts(null));
    api.watch().then((r) => setWatch({ ...EMPTY, ...r.watch })).catch(() => null);
  }, []);

  const toggle = (k: WatchKind, v: string) =>
    setWatch((w) => ({ ...w, [k]: w[k].includes(v) ? w[k].filter((x) => x !== v) : [...w[k], v] }));

  async function save() {
    try {
      const r = await api.saveWatch(watch);
      setWatch({ ...EMPTY, ...r.watch });
      setNote("Saved. New alerts appear after the next change detection that touches this scope.");
      onSaved?.();
    } catch (e) {
      setNote((e as Error).message);
    }
  }

  if (!opts) return <p className="text-sm text-ink-muted">Loading…</p>;
  const methods = [...new Map(opts.methods.map((m) => [m.code, m])).values()];
  const dupe = (label: string) => methods.filter((m) => m.label === label).length > 1;   // e.g. Direct Selection (DIR, DS)
  return (
    <div className="space-y-3 text-sm">
      <p className="text-xs text-ink-muted">
        Pick what you follow. Within a row any choice matches; across rows all must (Kenya + Civil Works = Kenyan civil
        works). A project you add is followed on its own.
      </p>
      <Chips label="Countries" values={opts.countries.map((c) => [c.code, c.name])} chosen={watch.country} onToggle={(v) => toggle("country", v)} />
      <Chips label="What is bought" values={opts.procGroups.map((g) => [g.code, g.label])} chosen={watch.proc_group} onToggle={(v) => toggle("proc_group", v)} />
      <Chips label="Methods" values={methods.map((m) => [m.code, dupe(m.label) ? `${m.label} (${m.code})` : m.label])} chosen={watch.method} onToggle={(v) => toggle("method", v)} />
      <Chips label="Sectors" values={opts.sectors.map((s) => [s, s])} chosen={watch.sector} onToggle={(v) => toggle("sector", v)} />
      <div>
        <p className="mb-1 text-xs font-medium text-ink-muted">Projects</p>
        <div className="flex flex-wrap items-center gap-2">
          {watch.project.map((p) => (
            <button key={p} className="rounded-full bg-brand-soft px-2 py-0.5 text-xs" onClick={() => toggle("project", p)}>{p} ×</button>
          ))}
          <input className="w-32 rounded-md border border-line bg-surface px-2 py-1 text-xs" placeholder="P123456" value={project}
            onChange={(e) => setProject(e.target.value.toUpperCase())}
            onKeyDown={(e) => { if (e.key === "Enter" && /^P\d{6}$/.test(project)) { toggle("project", project); setProject(""); } }} />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button className="rounded-md bg-brand px-3 py-1.5 text-sm text-white dark:text-black" onClick={save}>Save watch-list</button>
        {note && <span className="text-xs text-ink-muted">{note}</span>}
      </div>
    </div>
  );
}

function Chips({ label, values, chosen, onToggle }: { label: string; values: [string, string][]; chosen: string[]; onToggle: (v: string) => void }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-ink-muted">{label}</p>
      <div className="flex max-h-28 flex-wrap gap-1 overflow-auto">
        {values.map(([v, text]) => (
          <button key={v} aria-pressed={chosen.includes(v)} onClick={() => onToggle(v)}
            className={`rounded-full border px-2 py-0.5 text-xs ${chosen.includes(v) ? "border-brand bg-brand-soft" : "border-line"}`}>
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
