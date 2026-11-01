"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api/client";
import type { AssessRequest, AssessResponse, SharedItem } from "@/lib/api/types";
import { PlanArtifact } from "@/components/plan/plan-artifact";
import { AssessResults } from "@/app/assess/assess-view";
import { ExportButtons } from "@/components/export-buttons";

/** A temporary link (/shared?id=...): the plan or assessment it holds, with its export (and, for a plan, an editor). */
function Shared() {
  const id = useSearchParams().get("id");
  const [item, setItem] = useState<SharedItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!id) return;
    api.share(id).then(setItem).catch(() => setError("This link has expired or does not exist. Ask for a new one from the chat."));
  }, [id]);
  if (!id) return <NoLink />;
  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!item) return <p className="text-sm text-ink-muted">Loading…</p>;
  if (item.kind === "plan") return <PlanArtifact share={item} />;
  const body = item.body as { request: AssessRequest; response: AssessResponse };
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <h1 className="text-xl font-semibold">Package assessment · {body.request.countryCode} · {body.request.procGroup} · {body.request.methodCode}</h1>
      <ExportButtons kind="assessment" body={body} />
      <AssessResults r={body.response} />
    </div>
  );
}

/** Reached without a plan id (for example after signing in from an old address): the plan this browser last made, if
 * any (the chat keeps its link id under procintel-plan-link), and the way to make one. */
function NoLink() {
  const [last, setLast] = useState<string | null>(null);
  useEffect(() => {
    try { setLast(localStorage.getItem("procintel-plan-link")); } catch { /* storage blocked */ }
  }, []);
  return (
    <div className="space-y-3 text-sm">
      <p className="text-ink-muted">This page shows a plan or an assessment from its link, and the address has none.</p>
      <div className="flex flex-wrap gap-2">
        {last && <Link href={`/shared?id=${encodeURIComponent(last)}`} className="rounded-md bg-brand px-3 py-1.5 text-on-brand">Open your latest plan</Link>}
        <Link href="/plan" className="rounded-md border border-line px-3 py-1.5">Go to the Planning workspace</Link>
      </div>
    </div>
  );
}

export default function SharedPage() {
  return <Suspense fallback={<p className="text-sm text-ink-muted">Loading…</p>}><Shared /></Suspense>;
}
