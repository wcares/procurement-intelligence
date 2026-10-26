"use client";

import { useState } from "react";
import { api } from "@/lib/api/client";
import type { AssessRequest, RecommendationsResponse } from "@/lib/api/types";

/** Asked on request (about a minute: one cited answer per flagged risk). Accept / dismiss are ratings on the logged
 * response, like the feedback on answers. */
export function Recommendations({ request }: { request: AssessRequest | null }) {
  const [data, setData] = useState<RecommendationsResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rated, setRated] = useState<Record<string, string>>({});

  async function load() {
    if (!request) return;
    setBusy(true);
    setError(null);
    try {
      setData(await api.recommendations(request));
      setRated({});
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function rate(id: string, accept: boolean) {
    if (!data) return;
    await api.feedback({ responseId: data.meta.responseId, rating: accept ? "useful" : "not_useful",
      comment: `${accept ? "accepted" : "dismissed"} recommendation ${id}` }).catch(() => null);
    setRated((r) => ({ ...r, [id]: accept ? "accepted" : "dismissed" }));
  }

  if (!request) return <p className="text-xs text-muted">Assess a package to get recommendations for it.</p>;
  if (!data) {
    return (
      <div className="text-xs">
        <button className="rounded-md border border-line px-2 py-1" onClick={load} disabled={busy}>
          {busy ? "Looking at past projects…" : "Suggest actions for this package"}
        </button>
        <p className="mt-1 text-muted">From statistics and quoted lessons only; takes about a minute.</p>
        {error && <p className="mt-1 text-risk-high">{error}</p>}
      </div>
    );
  }
  if (data.recommendations.length === 0) return <p className="text-xs text-muted">No recommendation: the evidence does not support one for this package.</p>;
  return (
    <ul className="space-y-2">
      {data.recommendations.map((r) => (
        <li key={r.id} className="rounded-lg border border-line bg-surface p-3 text-xs">
          <p className="font-medium text-sm">{r.title}</p>
          {r.text && <p className="mt-1">{r.text}</p>}
          {r.sentences?.map((s, i) => (
            <p key={i} className="mt-1">
              {s.text}{" "}
              {s.citations.map((c) => {
                const cit = r.citations[c];
                return cit ? (
                  <a key={c} href={cit.url} target="_blank" rel="noreferrer" className="text-accent" title={`${cit.projectName}: ${cit.quote.slice(0, 200)}`}>[{cit.projectName || cit.projectId}]</a>
                ) : null;
              })}
            </p>
          ))}
          {r.note && <p className="mt-1 text-muted">{r.note}</p>}
          <p className="mt-1 text-muted">Basis: {r.basis === "statistic" ? "award-time statistics" : "passages from past project reports"}</p>
          <div className="mt-1 flex gap-3">
            {rated[r.id] ? <span className="text-muted">{rated[r.id]}</span> : (
              <>
                <button className="underline" onClick={() => rate(r.id, true)}>accept</button>
                <button className="underline" onClick={() => rate(r.id, false)}>dismiss</button>
              </>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
