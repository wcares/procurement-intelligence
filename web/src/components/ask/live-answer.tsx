"use client";

import type { AskEvent } from "@/lib/api/types";

/** What an answer has so far: what is being done, the evidence found, and the sentences written and checked. */
export interface Live {
  stage: string;
  passages: Extract<AskEvent, { type: "passages" }>["items"];
  sentences: string[];
}
export const emptyLive: Live = { stage: "Searching the reports…", passages: [], sentences: [] };

/** Folds one event into what is shown. */
export function fold(l: Live, e: AskEvent): Live {
  if (e.type === "stage") return { ...l, stage: e.text };
  if (e.type === "passages") return { ...l, passages: e.items };
  if (e.type === "sentence") return { ...l, sentences: [...l.sentences, e.text] };
  return l;
}

/** The answer while it is still being worked out: replaced by the full answer, with its sources, when that is ready. */
export function LiveAnswer({ live }: { live: Live }) {
  const where = [...new Set(live.passages.map((p) => `${p.projectName || p.projectId} (${p.countryCode})`))];
  return (
    <div className="space-y-2" aria-live="polite">
      <p className="flex items-center gap-2 text-sm text-ink-muted">
        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-brand" aria-hidden />
        {live.stage}
      </p>
      {where.length > 0 && (
        <p className="text-xs text-ink-muted">Evidence found in: {where.slice(0, 4).join("; ")}{where.length > 4 ? ` and ${where.length - 4} more` : ""}.</p>
      )}
      {live.sentences.length > 0 && (
        <div className="rounded-xl border border-line bg-surface px-4 py-3 text-sm leading-relaxed">
          {live.sentences.map((t, i) => <span key={i}>{t} </span>)}
          <span className="text-xs text-ink-muted">Sources are added when the answer is complete.</span>
        </div>
      )}
    </div>
  );
}
