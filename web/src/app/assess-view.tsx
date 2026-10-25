"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { AssessRequest, AssessResponse, Options, ProcGroup, SimilarPackage } from "@/lib/api/types";
import { Caveats, CitationCard, RiskBadge, TimelineBar } from "@/components/evidence";
import { FeedbackBar, FlagCitation } from "@/components/feedback";

const CPIA_LABELS: Record<string, string> = {
  transparency_corruption: "Transparency & corruption",
  public_administration: "Public administration",
  public_sector_mgmt_cluster: "Public sector mgmt (cluster)",
  property_rights_rule_based_gov: "Rule-based governance",
  business_regulatory_env: "Business regulation",
  ida_allocation_index: "IDA allocation index",
};

const field = "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-accent";

export function AssessView() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [form, setForm] = useState<AssessRequest>({ countryCode: "KE", procGroup: "CW", methodCode: "RFB", description: "" });
  const [result, setResult] = useState<AssessResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.options().then(setOpts).catch((e: Error) => setError(e.message));
  }, []);

  const methods = useMemo(
    () => opts?.methods.filter((m) => m.procGroups.includes(form.procGroup)) ?? [],
    [opts, form.procGroup],
  );

  const regions = useMemo(() => {
    const by = new Map<string, Options["countries"]>();
    for (const c of opts?.countries ?? []) by.set(c.region, [...(by.get(c.region) ?? []), c]);
    return [...by.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [opts]);

  function setGroup(g: ProcGroup) {
    const first = opts?.methods.find((m) => m.procGroups.includes(g));
    setForm((f) => ({ ...f, procGroup: g, methodCode: methods.some((m) => m.code === f.methodCode && m.procGroups.includes(g)) ? f.methodCode : (first?.code ?? "") }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResult(await api.assess(form));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[340px_1fr]">
      <form onSubmit={submit} className="space-y-4 self-start rounded-xl border border-line bg-surface p-5 lg:sticky lg:top-6">
        <h2 className="font-semibold">Describe the package</h2>
        <Label text="Country">
          <select className={field} value={form.countryCode} onChange={(e) => setForm({ ...form, countryCode: e.target.value })} disabled={!opts}>
            {regions.map(([region, cs]) => (
              <optgroup key={region} label={region}>
                {cs.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </Label>
        <Label text="What is being bought">
          <select className={field} value={form.procGroup} onChange={(e) => setGroup(e.target.value as ProcGroup)} disabled={!opts}>
            {opts?.procGroups.map((g) => (
              <option key={g.code} value={g.code}>
                {g.label}
              </option>
            ))}
          </select>
        </Label>
        <Label text="Procurement method">
          <select className={field} value={form.methodCode} onChange={(e) => setForm({ ...form, methodCode: e.target.value })} disabled={!opts}>
            {methods.map((m) => (
              <option key={m.code} value={m.code}>
                {m.label} ({m.code})
              </option>
            ))}
          </select>
        </Label>
        <Label text="Sector (optional)">
          <select className={field} value={form.sector ?? ""} onChange={(e) => setForm({ ...form, sector: e.target.value || undefined })} disabled={!opts}>
            <option value="">Any</option>
            {opts?.sectors.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </Label>
        <Label text="Short description (optional)">
          <textarea
            className={`${field} min-h-20`}
            placeholder="e.g. rehabilitation of rural feeder roads"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </Label>
        <button
          type="submit"
          disabled={!opts || !form.methodCode || loading}
          className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50 dark:text-black"
        >
          {loading ? "Assessing…" : "Assess package"}
        </button>
      </form>

      <section className="min-w-0 space-y-6">
        {error && <p className="rounded-lg bg-risk-high-soft px-4 py-3 text-sm text-risk-high">{error}</p>}
        {!result && !error && (
          <div className="rounded-xl border border-dashed border-line p-10 text-center text-muted">
            Describe a procurement package to see how comparable packages went: timeline, risks, and quoted lessons from past
            evaluations.
          </div>
        )}
        {result && <Results r={result} />}
      </section>
    </div>
  );
}

function Results({ r }: { r: AssessResponse }) {
  return (
    <>
      <Caveats meta={r.meta} />
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Expected timeline">
          {r.timeline ? <TimelineBar t={r.timeline} /> : <p className="text-sm text-muted">Not enough comparable packages.</p>}
        </Card>
        <Card title="Risk flags">
          {r.risks.length === 0 ? (
            <p className="text-sm text-muted">No flags from the available statistics.</p>
          ) : (
            <ul className="space-y-3">
              {r.risks.map((f) => (
                <li key={f.id}>
                  <div className="flex items-center gap-2">
                    <RiskBadge level={f.level} />
                    <span className="text-sm font-medium">{f.label}</span>
                  </div>
                  <p className="mt-1 text-sm text-muted">{f.detail}</p>
                  <p className="mt-0.5 text-xs text-muted">Basis: {f.basis === "statistic" ? "historical statistic" : "model estimate"}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      {r.governance.length > 0 && (
        <Card title="Country governance (CPIA, 1 = low, 6 = high)">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {r.governance.map((g) => (
              <div key={g.indicator}>
                <dt className="text-xs text-muted">{CPIA_LABELS[g.indicator] ?? g.indicator}</dt>
                <dd className="text-sm font-medium tabular-nums">
                  {g.value.toFixed(1)} <span className="text-xs font-normal text-muted">({g.year})</span>
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      )}
      {r.similarPackages.length > 0 && <SimilarPackages items={r.similarPackages} />}
      <div>
        <h3 className="mb-3 font-semibold">Lessons from comparable projects</h3>
        {r.precedents.length === 0 ? (
          <p className="text-sm text-muted">No relevant passages found.</p>
        ) : (
          <div className="space-y-3">
            {r.precedents.map((p, i) => (
              <div key={p.citation.id}>
                <p className="mb-1 text-xs text-muted">Matched on: {p.matchedOn.join(" · ")}</p>
                <CitationCard c={p.citation} index={i} action={<FlagCitation responseId={r.meta.responseId} citationId={p.citation.id} />} />
              </div>
            ))}
          </div>
        )}
      </div>
      <FeedbackBar responseId={r.meta.responseId} subject="assessment" />
    </>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-5">
      <h3 className="mb-4 text-sm font-semibold text-muted">{title}</h3>
      {children}
    </div>
  );
}

function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-muted">{text}</span>
      {children}
    </label>
  );
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

function SimilarPackages({ items }: { items: SimilarPackage[] }) {
  return (
    <div>
      <h3 className="mb-1 font-semibold">Similar past contracts</h3>
      <p className="mb-3 text-xs text-muted">Awarded packages whose description is closest to yours, and how long they took from tender to award.</p>
      <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
        {items.map((p) => (
          <li key={p.packageId} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3 text-sm">
            <span className="min-w-0 flex-1 basis-64">{p.description}</span>
            <span className="text-xs text-muted">
              {p.projectId} · {p.countryCode} · {p.method}
            </span>
            <span className="tabular-nums">{p.tenderToAwardDays != null ? `${p.tenderToAwardDays} days` : "time not known"}</span>
            {p.valueUsd != null && <span className="tabular-nums text-muted">{usd.format(p.valueUsd)}</span>}
            {p.rebid && <span className="rounded bg-risk-medium-soft px-1.5 py-0.5 text-xs text-risk-medium">re-tendered</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
