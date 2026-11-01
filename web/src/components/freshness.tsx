"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { SourceFreshness } from "@/lib/api/types";

const ago = (h: number | null) => (h == null ? "never" : h < 1 ? `${Math.max(1, Math.round(h * 60))} min ago` : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} days ago`);

/** One line: when each source behind the numbers was last read; a late source is shown in red. */
export function Freshness({ only }: { only?: string[] }) {
  const [rows, setRows] = useState<SourceFreshness[] | null>(null);
  useEffect(() => {
    api.freshness().then((r) => setRows(r.sources)).catch(() => setRows([]));
  }, []);
  const shown = (rows ?? []).filter((s) => !only || only.includes(s.entity));
  if (!shown.length) return null;
  return (
    <p className="text-[11px] text-ink-muted">
      Data read:{" "}
      {shown.map((s, i) => (
        <span key={s.entity} className={s.late ? "text-risk-high" : undefined} title={s.lastRead ? `last good read ${s.lastRead}; read every ${s.everyHours} h` : "not read yet"}>
          {i > 0 && " · "}{s.label} {ago(s.hoursAgo)}{s.late ? " (late)" : ""}
        </span>
      ))}
    </p>
  );
}
