"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { FeedbackReviewResponse } from "@/lib/api/types";

const REVIEW_LABELS: Record<string, string> = {
  flagged_citation: "Citation flagged as wrong",
  refused_question: "Question refused",
  not_useful: "Rated not useful",
};

export function FeedbackReview() {
  const [data, setData] = useState<FeedbackReviewResponse | null>(null);
  useEffect(() => {
    api.feedbackReview().then(setData).catch(() => setData(null));
  }, []);
  if (!data) return null;
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Feedback to review</h2>
      <div className="space-y-3 rounded-xl border border-line bg-surface p-4">
        <p className="text-xs text-muted">
          Built by the feedback review job. Refused and not-useful questions are candidates for the evaluation set; a
          passage flagged as a wrong citation on {data.demoteAfter} or more separate answers is moved to the end of search
          results ({data.demoted.length} now).
        </p>
        {data.items.length === 0 ? (
          <p className="text-sm text-muted">Nothing to review yet.</p>
        ) : (
          <ul className="divide-y divide-line text-sm">
            {data.items.slice(0, 15).map((it) => (
              <li key={`${it.kind}:${it.key}`} className="py-1.5">
                <span className="font-medium">{REVIEW_LABELS[it.kind] ?? it.kind}</span>
                <span className="text-xs text-muted">
                  {" "}
                  · {it.responses} response{it.responses === 1 ? "" : "s"}
                  {it.kind === "flagged_citation" && <> · passage <span className="font-mono">{it.key}</span></>}
                  {data.demoted.includes(it.key) && " · demoted"}
                </span>
                <p className="text-xs text-muted">{it.questions.join(" | ")}</p>
                {it.comments.length > 0 && <p className="text-xs italic text-muted">“{it.comments.join("” “")}”</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
