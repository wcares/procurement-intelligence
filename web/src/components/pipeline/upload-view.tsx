"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { Upload, UploadsResponse } from "@/lib/api/types";
import { when } from "./when";

const WORKING = new Set(["received", "extracted", "classified", "linked"]);
const STATUS: Record<string, { label: string; cls: string }> = {
  added: { label: "added to the evidence", cls: "text-risk-low" },
  kept: { label: "kept and linked", cls: "text-foreground" },
  needs_review: { label: "needs review", cls: "text-risk-medium" },
  failed: { label: "failed", cls: "text-risk-high" },
  duplicate: { label: "duplicate", cls: "text-muted" },
};

/** Add a file and follow it: text extracted by format, kind decided, projects and countries linked; a completion
 * report linked to a tracked project is added to the evidence and its passages indexed by the pipeline. */
export function UploadView() {
  const [data, setData] = useState<UploadsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api.uploads().then(setData).catch((e) => setError((e as Error).message)), []);
  useEffect(() => {
    load();
  }, [load]);
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
        className={`rounded-xl border-2 border-dashed p-6 text-center text-sm ${drag ? "border-accent bg-accent-soft" : "border-line bg-surface"}`}
      >
        <p>Drop files here or{" "}
          <button className="underline" onClick={() => input.current?.click()} disabled={busy}>choose files</button>
        </p>
        <p className="mt-1 text-xs text-muted">
          {data ? `${data.formats.join(", ")} · up to ${data.maxMb} MB each` : ""}. Completion reports that name a tracked
          project are added to the evidence; other documents are kept, classified and linked. Scans need OCR, which is
          not available yet.
        </p>
        <input ref={input} type="file" multiple className="hidden" onChange={(e) => send(e.target.files)}
          accept={data?.formats.map((f) => `.${f}`).join(",")} />
        {busy && <p className="mt-2 text-xs text-muted">Uploading…</p>}
      </div>
      {error && <p className="text-sm text-risk-high">{error}</p>}
      {data && data.uploads.length === 0 && <p className="text-sm text-muted">No uploads yet.</p>}
      <ul className="space-y-3">{data?.uploads.map((u) => <UploadCard key={u.upload_id} u={u} />)}</ul>
    </div>
  );
}

function UploadCard({ u }: { u: Upload }) {
  const s = STATUS[u.status] ?? { label: "processing…", cls: "text-accent" };
  return (
    <li className="rounded-xl border border-line bg-surface p-4 text-sm">
      <header className="mb-2 flex flex-wrap items-baseline gap-x-3">
        <span className="font-semibold">{u.filename}</span>
        <span className="text-xs text-muted">{u.format} · {(u.size / 1024).toFixed(0)} KB · {when(u.uploaded_at)}</span>
        <span className={`ml-auto text-xs font-medium ${s.cls}`}>{s.label}</span>
      </header>
      <ol className="space-y-1 border-l border-line pl-3 text-xs">
        {u.stages.map((st, i) => (
          <li key={i}><span className="font-medium">{st.stage}</span> <span className="text-muted">· {st.detail}</span></li>
        ))}
      </ol>
      {u.links && u.links.projects.length > 0 && (
        <p className="mt-2 text-xs">
          Projects:{" "}
          {u.links.projects.map((p) => (
            <span key={p.id} className={`mr-2 ${p.known ? "" : "text-muted"}`}>{p.id}{p.name ? ` ${p.name}` : " (not tracked)"}</span>
          ))}
        </p>
      )}
      {u.doc_id && (
        <p className="mt-1 text-xs">
          In the evidence as <span className="font-mono">{u.doc_id}</span>; indexing shows in the{" "}
          <Link className="underline" href="/pipeline/events">event log</Link>.
        </p>
      )}
    </li>
  );
}
