"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { RecommendationHistory } from "@/lib/api/types";

const KIND_LABEL: Record<string, string> = { method: "Another method", mitigation: "What past projects did" };
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

/** Every recommendation the planner asked for on Assess and what they decided; accept / dismiss counts over everyone's
 * show which kinds of recommendation people find useful. */
export function PastRecommendations() {
  const [data, setData] = useState<RecommendationHistory | null>(null);
  useEffect(() => {
    api.recommendationHistory().then(setData).catch(() => setData(null));
  }, []);
  if (!data) return <p className="text-sm text-ink-muted">Loading…</p>;
  const kinds = Object.entries(data.totals);
  return (
    <div className="space-y-4">
      {kinds.length > 0 && (
        <table className="text-sm">
          <thead className="text-left text-xs text-ink-muted">
            <tr><th className="pr-6 font-normal">Kind (everyone)</th><th className="pr-6 font-normal">Shown</th><th className="pr-6 font-normal">Accepted</th><th className="font-normal">Dismissed</th></tr>
          </thead>
          <tbody className="tabular-nums">
            {kinds.map(([k, t]) => (
              <tr key={k}><td className="pr-6">{KIND_LABEL[k] ?? k}</td><td className="pr-6">{t.shown}</td><td className="pr-6">{t.accepted}</td><td>{t.dismissed}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {data.items.length === 0 ? (
        <p className="text-sm text-ink-muted">You have not asked for recommendations yet; they are on the Assess page.</p>
      ) : (
        <ul className="divide-y divide-line text-sm">
          {data.items.map((i) => (
            <li key={i.responseId} className="py-2">
              <p className="text-xs text-ink-muted">
                {day(i.at)} · {i.package.countryCode} · {i.package.procGroup} · {i.package.methodCode}
                {i.package.estimatedValueUsd ? ` · US$${Math.round(i.package.estimatedValueUsd).toLocaleString()}` : ""}
              </p>
              {i.recommendations.length === 0 ? (
                <p className="text-ink-muted">No recommendation: the evidence did not support one.</p>
              ) : (
                <ul>
                  {i.recommendations.map((r) => (
                    <li key={r.id} className="flex gap-2">
                      <span>{r.title}</span>
                      <span className={`text-xs ${r.decision === "accepted" ? "text-risk-low" : "text-ink-muted"}`}>
                        {r.decision ?? "no decision"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
