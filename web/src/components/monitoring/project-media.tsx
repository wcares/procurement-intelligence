"use client";

import { useEffect, useState } from "react";
import { API_BASE, api } from "@/lib/api/client";
import type { ProjectMedia } from "@/lib/api/types";

/** One photo or video, with what it is, when it was taken, which package it belongs to, and a demo label when made up. */
export function MediaTile({ m, onRemove }: { m: ProjectMedia; onRemove?: () => void }) {
  const src = `${API_BASE}${m.url}`;
  return (
    <figure className="w-44 shrink-0 overflow-hidden rounded-lg border border-line bg-surface text-xs">
      <a href={src} target="_blank" rel="noreferrer" className="relative block bg-subtle">
        {m.kind === "video" ? (
          <video src={src} controls preload="metadata" className="h-28 w-full object-cover" />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={m.caption ?? m.filename} loading="lazy" className="h-28 w-full object-cover" />
        )}
        {m.synthetic && (
          <span className="absolute left-1 top-1 rounded bg-risk-medium px-1.5 py-0.5 text-[10px] font-semibold uppercase text-white">
            Synthetic demo
          </span>
        )}
      </a>
      <figcaption className="space-y-0.5 p-2">
        <p className="line-clamp-2 font-medium">{m.caption || m.filename}</p>
        <p className="text-ink-muted">
          {m.projectId}{m.packageRef ? ` · ${m.packageRef}` : ""}{m.takenOn ? ` · ${m.takenOn}` : ""}
        </p>
        {onRemove && <button onClick={onRemove} className="text-ink-muted underline">remove</button>}
      </figcaption>
    </figure>
  );
}

/** A project's photos and videos, and a form to attach one (to the project, or to one of its packages). */
export function ProjectMediaPanel({ projectId, packages }: { projectId: string; packages: { id: string; label: string }[] }) {
  const [items, setItems] = useState<ProjectMedia[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [packageRef, setPackageRef] = useState("");
  const [caption, setCaption] = useState("");
  const [takenOn, setTakenOn] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = () => api.media([projectId]).then((r) => setItems(r.items)).catch(() => setItems([]));
  useEffect(() => { load(); }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const out = await api.uploadMedia(file, { projectId, packageRef, caption, takenOn });
    setBusy(false);
    if ("error" in out) return setError(out.error);
    setFile(null);
    setCaption("");
    (e.target as HTMLFormElement).reset();
    load();
  }

  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs font-medium">Photos and videos</p>
      {items === null ? <p className="text-xs text-ink-muted">Loading…</p> : items.length === 0 ? (
        <p className="text-xs text-ink-muted">None attached yet.</p>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {items.map((m) => <MediaTile key={m.id} m={m} onRemove={m.synthetic ? undefined : () => api.removeMedia(m.id).then(load).catch(() => setError("only the uploader or an admin can remove it"))} />)}
        </div>
      )}
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2 text-xs">
        <input type="file" accept="image/*,video/mp4,video/webm,video/quicktime" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="max-w-full" />
        <select value={packageRef} onChange={(e) => setPackageRef(e.target.value)} className="max-w-56 rounded border border-line bg-surface px-1 py-0.5">
          <option value="">the whole project</option>
          {packages.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        <input value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="What it shows" className="min-w-0 flex-1 rounded border border-line bg-surface px-1 py-0.5" />
        <input type="date" value={takenOn} onChange={(e) => setTakenOn(e.target.value)} className="rounded border border-line bg-surface px-1 py-0.5" />
        <button disabled={!file || busy} className="rounded bg-brand px-2 py-1 text-white disabled:opacity-50">{busy ? "Uploading…" : "Attach"}</button>
      </form>
      {error && <p className="text-xs text-risk-high">{error}</p>}
    </div>
  );
}

/** Photos and videos of the projects an answer cites (shown beside the answer; none: nothing is shown). */
export function RelatedMedia({ projectIds }: { projectIds: string[] }) {
  const [items, setItems] = useState<ProjectMedia[]>([]);
  const key = [...new Set(projectIds)].sort().join(",");
  useEffect(() => {
    if (key) api.media(key.split(",")).then((r) => setItems(r.items)).catch(() => setItems([]));
  }, [key]);
  if (!items.length) return null;
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium">Photos and videos from these projects</p>
      <div className="flex gap-2 overflow-x-auto pb-1">{items.map((m) => <MediaTile key={m.id} m={m} />)}</div>
    </div>
  );
}
