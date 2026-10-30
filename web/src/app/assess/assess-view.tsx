"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import type { AssessRequest, AssessResponse, FlagEvidenceItem, Options, ProcGroup } from "@/lib/api/types";
import { Caveats, CitationCard, RiskBadge, TimelineBar } from "@/components/evidence";
import { FeedbackBar, FlagCitation } from "@/components/feedback";
import { StageTimeline } from "@/components/assess/stage-timeline";
import { SimilarPackages } from "@/components/assess/similar-packages";
import { InsightsPanel } from "@/components/insights/insights-panel";
import { GoalPanel } from "@/components/assess/goal-panel";
import { StartedFields, StartedForecast, type Started } from "@/components/monitoring/started-forecast";

const CPIA_LABELS: Record<string, string> = {
  transparency_corruption: "Transparency & corruption",
  public_administration: "Public administration",
  public_sector_mgmt_cluster: "Public sector mgmt (cluster)",
  property_rights_rule_based_gov: "Rule-based governance",
  business_regulatory_env: "Business regulation",
  ida_allocation_index: "IDA allocation index",
};

const WGI_LABELS: Record<string, string> = {
  control_of_corruption: "Control of corruption",
  government_effectiveness: "Government effectiveness",
  political_stability: "Political stability",
  regulatory_quality: "Regulatory quality",
  rule_of_law: "Rule of law",
  voice_accountability: "Voice & accountability",
};

const field = "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand";

export function AssessView() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [form, setForm] = useState<AssessRequest>({ countryCode: "KE", procGroup: "CW", methodCode: "RFB", description: "" });
  const [result, setResult] = useState<AssessResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [assessed, setAssessed] = useState<AssessRequest | null>(null);
  const [started, setStarted] = useState<Started>({});
  const [startedAssessed, setStartedAssessed] = useState<Started | null>(null);

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
      setAssessed(form);
      setStartedAssessed(started.tenderStart || started.awardDate ? { ...started } : null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[340px_1fr]">
      <div className="space-y-4 self-start lg:sticky lg:top-6">
      <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-surface p-5">
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
        <Label text="Project id (optional)">
          <input
            className={field}
            placeholder="e.g. P179284"
            maxLength={20}
            value={form.projectId ?? ""}
            onChange={(e) => setForm({ ...form, projectId: e.target.value.trim().toUpperCase() || undefined })}
          />
          <span className="text-xs text-ink-muted">A tracked project&apos;s age and size sharpen the prediction.</span>
        </Label>
        <Label text="Estimated value, US$ (optional)">
          <input
            type="number"
            min={0}
            className={field}
            placeholder="e.g. 2000000"
            value={form.estimatedValueUsd ?? ""}
            onChange={(e) => setForm({ ...form, estimatedValueUsd: e.target.value ? Number(e.target.value) : undefined })}
          />
        </Label>
        <Label text="Short description (optional)">
          <textarea
            className={`${field} min-h-20`}
            placeholder="e.g. rehabilitation of rural feeder roads"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </Label>
        <Label text="Tender reference (optional)">
          <input
            className={field}
            placeholder="bid reference, e.g. KE-KURA-123456-CW-RFB"
            maxLength={120}
            value={form.tenderReference ?? ""}
            onChange={(e) => setForm({ ...form, tenderReference: e.target.value })}
          />
          <span className="text-xs text-ink-muted">Lets us check this prediction against the actual award time later.</span>
        </Label>
        <StartedFields value={started} onChange={setStarted} />
        <button
          type="submit"
          disabled={!opts || !form.methodCode || loading}
          className="w-full rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {loading ? "Assessing…" : "Assess package"}
        </button>
      </form>
      <InsightsPanel procGroup={form.procGroup} methodCode={form.methodCode} countryCode={form.countryCode} assessed={assessed} />
      </div>

      <section className="min-w-0 space-y-6">
        {error && <p className="rounded-lg bg-risk-high-soft px-4 py-3 text-sm text-risk-high">{error}</p>}
        {!result && !error && (
          <div className="rounded-xl border border-dashed border-line p-10 text-center text-ink-muted">
            Describe a procurement package to see how comparable packages went: timeline, risks, and quoted lessons from past
            evaluations. To plan toward a target (for example awarded within 90 days), assess the package first: a &ldquo;Set a
            goal&rdquo; panel then ranks the methods and lot counts that met it most often.
          </div>
        )}
        {result && assessed && startedAssessed && (
          <StartedForecast procGroup={assessed.procGroup} methodCode={assessed.methodCode} started={startedAssessed} />
        )}
        {result && assessed && <GoalPanel request={assessed} />}
        {result && <Results r={result} />}
      </section>
    </div>
  );
}

function Results({ r }: { r: AssessResponse }) {
  const show = (elementId: string) => {
    const el = document.getElementById(elementId);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.classList.add("ring-2", "ring-brand");
    setTimeout(() => el?.classList.remove("ring-2", "ring-brand"), 1500);
  };
  return (
    <>
      <Caveats meta={r.meta} />
      {r.stages && r.stages.length > 0 && (
        <Card title="Tender stages and where the risks are">
          <StageTimeline stages={r.stages} risks={r.risks} precedents={r.precedents} prediction={r.prediction} onSelect={show} />
        </Card>
      )}
      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Expected timeline">
          {r.timeline ? <TimelineBar t={r.timeline} /> : <p className="text-sm text-ink-muted">Not enough comparable packages.</p>}
        </Card>
        <Card title="Risk flags">
          {r.risks.length === 0 ? (
            <p className="text-sm text-ink-muted">No flags from the available statistics.</p>
          ) : (
            <ul className="space-y-3">
              {r.risks.map((f) => (
                <li key={f.id} id={`flag-${f.id}`} className="rounded-md p-1 transition-shadow">
                  <div className="flex items-center gap-2">
                    <RiskBadge level={f.level} />
                    <span className="text-sm font-medium">{f.label}</span>
                  </div>
                  <p className="mt-1 text-sm text-ink-muted">{f.detail}</p>
                  <p className="mt-0.5 text-xs text-ink-muted">Basis: {f.basis === "statistic" ? "historical statistic" : "model estimate"}</p>
                  {f.evidence && f.evidence.length > 0 && <FlagEvidence items={f.evidence} />}
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
                <dt className="text-xs text-ink-muted">{CPIA_LABELS[g.indicator] ?? g.indicator}</dt>
                <dd className="text-sm font-medium tabular-nums">
                  {g.value.toFixed(1)} <span className="text-xs font-normal text-ink-muted">({g.year})</span>
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      )}
      {r.governance.length === 0 && (r.wgi?.length ?? 0) > 0 && (
        <Card title="Country governance (WGI, 0 = world average, about −2.5 to +2.5)">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {r.wgi!.map((g) => (
              <div key={g.indicator}>
                <dt className="text-xs text-ink-muted">{WGI_LABELS[g.indicator] ?? g.indicator}</dt>
                <dd className="text-sm font-medium tabular-nums">
                  {g.value > 0 ? "+" : ""}
                  {g.value.toFixed(2)} <span className="text-xs font-normal text-ink-muted">({g.year})</span>
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
          <p className="text-sm text-ink-muted">No relevant passages found.</p>
        ) : (
          <div className="space-y-3">
            {r.precedents.map((p, i) => (
              <div key={p.citation.id}>
                <p className="mb-1 text-xs text-ink-muted">Matched on: {p.matchedOn.join(" · ")}</p>
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
      <h3 className="mb-4 text-sm font-semibold text-ink-muted">{title}</h3>
      {children}
    </div>
  );
}

function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-ink-muted">{text}</span>
      {children}
    </label>
  );
}

function FlagEvidence({ items }: { items: FlagEvidenceItem[] }) {
  return (
    <details className="mt-1">
      <summary className="cursor-pointer text-xs text-ink-muted">Evidence ({items.length})</summary>
      <ul className="mt-1 space-y-1 border-l pl-3">
        {items.map((e) => (
          <li key={e.ref} className="text-xs">
            {e.url ? (
              <a href={e.url} target="_blank" rel="noreferrer" className="underline">
                {e.label}
              </a>
            ) : (
              <span>{e.label}</span>
            )}
            <span className="text-ink-muted"> · {e.detail}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
