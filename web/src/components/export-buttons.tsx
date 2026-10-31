"use client";

import { useState } from "react";
import { API_BASE } from "@/lib/api/client";

/** "Word" downloads the backend's .docx of what the page shows (POST /export/<kind>); "PDF" opens the browser's print
 * dialog, where "Save as PDF" keeps the page's print layout (navigation, forms and the chat are left out). */
export function ExportButtons({ kind, body }: { kind: "plan" | "assessment"; body: unknown }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function word() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/export/${kind}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? `export failed (${res.status})`);
      const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? `${kind}.docx`;
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement("a"), { href: url, download: name });
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const btn = "rounded-lg border border-line px-2.5 py-1 text-xs font-medium hover:bg-subtle disabled:opacity-50";
  return (
    <div className="flex flex-wrap items-center gap-2 print:hidden">
      <span className="text-xs text-ink-muted">Export {kind === "plan" ? "the plan" : "this assessment"}:</span>
      <button type="button" onClick={word} disabled={busy} className={btn}>{busy ? "Making…" : "Word (.docx)"}</button>
      <button type="button" onClick={() => window.print()} className={btn}>PDF (print)</button>
      {error && <span className="text-xs text-risk-high">{error}</span>}
    </div>
  );
}
