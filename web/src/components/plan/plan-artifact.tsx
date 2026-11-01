"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { SharedItem } from "@/lib/api/types";
import { ExportButtons } from "@/components/export-buttons";
import { Freshness } from "@/components/freshness";
import { PackageCard } from "./package-card";
import { PlanResults } from "./plan-results";
import { PlanSettings } from "./plan-settings";
import { keepForChat, newPackage, usePlan, type PlanSnapshot } from "./use-plan";

const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/** A plan behind a link: the forecast as it was shared, its export, and an editor that forecasts again and saves the
 * plan behind the same link (or as a new link when it is someone else's). */
export function PlanArtifact({ share }: { share: SharedItem }) {
  const s = usePlan(share.body as unknown as PlanSnapshot);
  const [editing, setEditing] = useState(false);
  const [link, setLink] = useState(share);
  const [note, setNote] = useState<string | null>(null);
  const [newer, setNewer] = useState(false);
  // the chat saves its changes behind this link: show them (at once, or on request while the plan is being edited here)
  useEffect(() => {
    const t = setInterval(() => {
      api.share(link.id).then((r) => {
        if (r.createdAt === link.createdAt) return;
        if (editing) setNewer(true); else window.location.reload();
      }).catch(() => null);
    }, 15000);
    return () => clearInterval(t);
  }, [link.id, link.createdAt, editing]);
  if (!s.ready) return <p className="text-sm text-ink-muted">Loading…</p>;
  const country = s.opts?.countries.find((c) => c.code === s.countryCode)?.name ?? s.countryCode;
  const snapshot = (): PlanSnapshot & { plan: typeof s.plan } => ({ countryCode: s.countryCode, projectStart: s.projectStart, deadline: s.deadline, packages: s.packages, forecasts: s.forecasts, plan: s.plan });
  const stale = s.packages.some((p) => !s.forecasts[p.id]);

  async function save() {
    setNote(null);
    try {
      const out = await api.updateShare(link.id, snapshot());
      if ("error" in out) throw new Error(out.error);
      setLink(out); setNote("Saved: this link now shows the edited plan.");
    } catch {
      const made = await api.createShare("plan", snapshot());
      if ("error" in made) return setNote(made.error);
      window.history.replaceState(null, "", `/shared?id=${made.id}`);
      setLink(made); setNote("This link is someone else's, so the edited plan was saved as a new link (the address above).");
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold">Procurement plan · {country}</h1>
        <p className="text-xs text-ink-muted">
          Shared {when(link.createdAt)}{link.createdBy ? ` by ${link.createdBy}` : ""} · the link works until {when(link.expiresAt)} for signed-in users ·
          start {s.projectStart}{s.deadline ? ` · deadline ${s.deadline}` : ""}
        </p>
      </header>
      <div className="flex flex-wrap items-center gap-3 print:hidden">
        <ExportButtons kind="plan" body={snapshot()} />
        <button type="button" onClick={() => setEditing(!editing)} className="rounded-lg border border-line px-2.5 py-1 text-xs font-medium hover:bg-subtle">
          {editing ? "Done editing" : "Edit the plan"}
        </button>
        <Link href="/plan" onClick={() => keepForChat(s)} className="text-xs underline">Continue in the chat</Link>
      </div>
      {editing && (
        <section className="space-y-3 print:hidden">
          <PlanSettings s={s} />
          {s.packages.map((p) => (
            <PackageCard key={p.id} pkg={p} others={s.packages.filter((o) => o.id !== p.id)} opts={s.opts} countryCode={s.countryCode}
              forecast={s.forecasts[p.id]} status={s.errors[p.id]} onChange={s.update} onRemove={() => s.remove(p.id)} />
          ))}
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="rounded-md border border-line px-3 py-2 text-sm" onClick={() => s.setPackages((ps) => [...ps, newPackage()])}>Add a package</button>
            <button type="button" disabled={!s.opts || s.running || s.packages.length === 0}
              className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50" onClick={() => void s.run()}>
              {s.running ? s.progress || "Forecasting…" : "Forecast again"}
            </button>
            <button type="button" disabled={s.running || stale} onClick={() => void save()}
              className="rounded-md border border-brand px-3 py-2 text-sm text-brand disabled:opacity-50" title={stale ? "Forecast the edited plan first" : undefined}>
              Save to this link
            </button>
          </div>
        </section>
      )}
      {note && <p className="text-xs text-ink-muted">{note}</p>}
      {newer && (
        <p className="rounded-lg bg-risk-medium-soft px-3 py-2 text-xs text-risk-medium">
          The chat changed this plan while you were editing. <button className="underline" onClick={() => window.location.reload()}>Show the chat&apos;s version</button> (your unsaved edits here are dropped), or save yours.
        </p>
      )}
      {stale && !s.running && <p className="text-xs text-risk-medium">Some packages changed since the forecast: forecast again to update the dates.</p>}
      <PlanResults packages={s.packages} plan={s.plan} forecasts={s.forecasts} projectStart={s.projectStart} deadline={s.deadline} countryCode={s.countryCode} />
      <Freshness only={["Notice", "ContractAward", "Project"]} />
      <p className="text-xs text-ink-muted">
        Each forecast comes from comparable past packages; the project dates combine them in the order set. Treat the project
        dates as a planning aid: the system has not learned how packages depend on each other.
      </p>
    </div>
  );
}
