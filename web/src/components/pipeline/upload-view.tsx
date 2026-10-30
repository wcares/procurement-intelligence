"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api/client";
import type { Upload, UploadsResponse } from "@/lib/api/types";
import { when } from "./when";

// kinds that can join the evidence (the backend checks the title: an ISR, not an aide-memoire; a restructuring paper,
// not a contract amendment)
const EVIDENCE_KINDS = new Set(["completion_report", "supervision_report", "amendment"]);
const WORKING = new Set(["received", "extracted", "classified", "linked"]);
const STATUS: Record<string, { label: string; cls: string }> = {
  added: { label: "added to the evidence", cls: "text-risk-low" },
  kept: { label: "kept and linked", cls: "text-foreground" },
  needs_review: { label: "needs review", cls: "text-risk-medium" },
  failed: { label: "failed", cls: "text-risk-high" },
  duplicate: { label: "duplicate", cls: "text-ink-muted" },
  removed: { label: "removed", cls: "text-ink-muted" },
  awaiting_approval: { label: "waiting for an admin", cls: "text-risk-medium" },
};

/** Add a file and follow it: text extracted by format, kind decided, projects and countries linked; a completion
 * report linked to a tracked project is added to the evidence and its passages indexed by the pipeline. Planners see
 * their own uploads and their reports wait for an admin; admins see every upload and can add waiting reports. */
export function UploadView() {
  const [data, setData] = useState<UploadsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [showRemoved, setShowRemoved] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api.uploads().then(setData).catch((e) => setError((e as Error).message)), []);
  useEffect(() => {
    load();
  }, [load]);
  // a removed document leaves the list; its record is kept as history and shown on request
  const removed = data?.uploads.filter((u) => u.status === "removed").length ?? 0;
  const shown = data?.uploads.filter((u) => showRemoved || u.status !== "removed") ?? [];
  const working = data?.uploads.some((u) => WORKING.has(u.status)) ?? false;
  useEffect(() => {
    if (!working) return;
    const t = setInterval(load, 2000);   // follow the stages while any upload is still being processed
    return () => clearInterval(t);
  }, [working, load]);

  async function send(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError(null);
    for (const f of Array.from(files)) {
      const r = await api.upload(f).catch((e) => ({ error: (e as Error).message }));
      if (!("upload_id" in r)) setError(`${f.name}: ${r.error}`);
    }
    setBusy(false);
    load();
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => (e.preventDefault(), setDrag(true))}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => (e.preventDefault(), setDrag(false), send(e.dataTransfer.files))}
        className={`rounded-xl border-2 border-dashed p-6 text-center text-sm ${drag ? "border-brand bg-brand-soft" : "border-line bg-surface"}`}
      >
        <p>Drop files here or{" "}
          <button className="underline" onClick={() => input.current?.click()} disabled={busy}>choose files</button>
        </p>
        <p className="mt-1 text-xs text-ink-muted">
          {data ? `${data.formats.join(", ")} · up to ${data.maxMb} MB each` : ""}. Completion reports, supervision
          reports (ISRs) and restructuring papers that name a tracked project are added to the evidence{data && !data.all ? " once an admin confirms them" : ""}; other documents
          are kept, classified and linked. Scanned PDF pages are read by OCR.
        </p>
        <input ref={input} type="file" multiple className="hidden" onChange={(e) => send(e.target.files)}
          accept={data?.formats.map((f) => `.${f}`).join(",")} />
        {busy && <p className="mt-2 text-xs text-ink-muted">Uploading…</p>}
      </div>
      {error && <p className="text-sm text-risk-high">{error}</p>}
      {data && shown.length === 0 && <p className="text-sm text-ink-muted">No documents{removed ? " in the list" : " yet"}.</p>}
      <ul className="space-y-3">{shown.map((u) => <UploadCard key={u.upload_id} u={u} admin={data!.all} onChanged={load} />)}</ul>
      {removed > 0 && (
        <button type="button" className="text-xs text-ink-muted underline underline-offset-2" onClick={() => setShowRemoved((v) => !v)}>
          {showRemoved ? "Hide" : "Show"} removed documents ({removed})
        </button>
      )}
    </div>
  );
}

function UploadCard({ u, admin, onChanged }: { u: Upload; admin: boolean; onChanged: () => void }) {
  const s = STATUS[u.status] ?? { label: "processing…", cls: "text-brand" };
  const [asking, setAsking] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  async function remove() {
    try {
      await api.removeUpload(u.upload_id);
      onChanged();
    } catch (e) {
      setNote((e as Error).message);
    }
    setAsking(false);
  }
  async function approve() {
    const r = await api.approveUpload(u.upload_id).catch((e) => ({ error: (e as Error).message }));
    if ("error" in r) setNote(r.error);
    else onChanged();
  }
  const waiting = admin && EVIDENCE_KINDS.has(u.doc_type ?? "") && (u.status === "awaiting_approval" || u.status === "needs_review")
    && (u.links?.projects ?? []).some((p) => p.known);
  return (
    <li className="rounded-xl border border-line bg-surface p-4 text-sm">
      <header className="mb-2 flex flex-wrap items-baseline gap-x-3">
        <span className="font-semibold">{u.filename}</span>
        <span className="text-xs text-ink-muted">{u.format} · {(u.size / 1024).toFixed(0)} KB · {when(u.uploaded_at)}</span>
        <span className={`ml-auto text-xs font-medium ${s.cls}`}>{s.label}</span>
      </header>
      <ol className="space-y-1 border-l border-line pl-3 text-xs">
        {u.stages.map((st, i) => (
          <li key={i}><span className="font-medium">{st.stage}</span> <span className="text-ink-muted">· {st.detail}</span></li>
        ))}
      </ol>
      {u.links && u.links.projects.length > 0 && (
        <p className="mt-2 text-xs">
          Projects:{" "}
          {u.links.projects.map((p) => (
            <span key={p.id} className={`mr-2 ${p.known ? "" : "text-ink-muted"}`}>{p.id}{p.name ? ` ${p.name}` : " (not tracked)"}</span>
          ))}
        </p>
      )}
      {(u.links?.packages?.length ?? 0) > 0 && (
        <p className="mt-1 text-xs">
          Packages:{" "}
          {u.links!.packages!.map((p) => (
            <Link key={p.id} href={`/package?id=${encodeURIComponent(p.id)}`} className="mr-2 underline" title={p.description}>{p.ref}</Link>
          ))}
        </p>
      )}
      {(u.links?.firms?.length ?? 0) > 0 && (
        <p className="mt-1 text-xs">Firms: {u.links!.firms!.map((f) => f.name).join(" · ")}</p>
      )}
      {u.doc_id && u.status !== "removed" && (
        <p className="mt-1 text-xs">
          In the evidence as <span className="font-mono">{u.doc_id}</span>; indexing shows in the{" "}
          <Link className="underline" href="/pipeline/events">event log</Link>.
        </p>
      )}
      {u.status !== "removed" && !WORKING.has(u.status) && (
        <div className="mt-2 flex items-center gap-2 text-xs">
          {waiting && !asking && (
            <Button variant="outline" size="xs" className="border-line" onClick={approve}>Add to the evidence</Button>
          )}
          {asking ? (
            <>
              <span>
                Delete the file{u.doc_id ? " and take its report out of the evidence" : ""}? It leaves this list; a record is kept as history (Show removed documents).
              </span>
              <Button variant="outline" size="xs" className="border-line text-risk-high" onClick={remove}>Remove</Button>
              <Button variant="ghost" size="xs" onClick={() => setAsking(false)}>Keep</Button>
            </>
          ) : (
            <Button variant="ghost" size="xs" className="text-ink-muted" onClick={() => setAsking(true)}>Remove…</Button>
          )}
          {note && <span className="text-risk-high">{note}</span>}
        </div>
      )}
    </li>
  );
}
