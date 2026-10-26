import type { EvaluationResponse } from "@/lib/api/types";

const NAMES: Record<string, [string, (v: number) => string, "lower" | "higher"]> = {
  days_p50_mae: ["Typical time: error (days)", (v) => v.toFixed(0), "lower"],
  days_p90_pinball: ["Slow case: pinball loss", (v) => v.toFixed(1), "lower"],
  days_p90_coverage: ["Slow case: share below it", (v) => `${Math.round(v * 100)}%`, "higher"],
  over_180_brier: ["Over 180 days: Brier score", (v) => v.toFixed(3), "lower"],
  over_180_auc: ["Over 180 days: AUC", (v) => v.toFixed(2), "higher"],
};
const USES: Record<string, string> = { days_p50: "typical time", days_p90: "slow case", over_180: "over 180 days" };

/** The timeline model at each retrain: cross-validated error against the baseline (the median of comparable
 * packages), where the model is used, and the latest drift checks. */
export function ModelsView({ data }: { data: EvaluationResponse["models"] }) {
  return (
    <div className="space-y-4">
      {data.retrains.length === 0 ? <p className="text-sm text-ink-muted">No model trained yet.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-ink-muted">
              <tr><th className="py-1 pr-2">Trained</th><th className="pr-2">Packages</th>
                {Object.values(NAMES).map(([n]) => <th key={n} className="pr-2">{n}<br /><span className="font-normal">model / baseline</span></th>)}
                <th>Used for</th></tr>
            </thead>
            <tbody>
              {[...data.retrains].reverse().map((r) => (
                <tr key={r.trained_at} className="border-t border-line align-top">
                  <td className="py-1 pr-2 whitespace-nowrap">{new Date(r.trained_at).toLocaleString()}{r.source && <div className="text-ink-muted">from {r.source}</div>}</td>
                  <td className="pr-2 tabular-nums">{r.n ?? "–"}{r.projects ? <span className="text-ink-muted"> ({r.projects} projects)</span> : null}</td>
                  {Object.entries(NAMES).map(([k, [, fmt, better]]) => {
                    const v = r.metrics[k];
                    if (!v) return <td key={k} className="pr-2">–</td>;
                    const wins = better === "lower" ? v[0] < v[1] : v[0] > v[1];
                    return <td key={k} className="pr-2 tabular-nums">{fmt(v[0])} / {fmt(v[1])} <span className="text-ink-muted">{wins ? "better" : "worse"}</span></td>;
                  })}
                  <td>{r.use ? Object.entries(r.use).filter(([, u]) => u).map(([k]) => USES[k] ?? k).join(", ") || "none (baseline everywhere)" : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div>
        <h3 className="mb-1 text-xs font-semibold">Drift checks (packages awarded after training, tested out of sample)</h3>
        {data.driftChecks.length === 0 ? <p className="text-xs text-ink-muted">None yet.</p> : (
          <ul className="space-y-0.5 text-xs">
            {data.driftChecks.map((d) => (
              <li key={d.at}>{new Date(d.at).toLocaleString()}: {d.why}{d.retrain ? " → retrain queued" : ""}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
