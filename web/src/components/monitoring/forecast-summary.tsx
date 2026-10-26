import type { LiveForecast } from "@/lib/api/types";

/** The forecast in words: when the award is expected and how sure, the contract end, warnings and caveats. */
export function ForecastSummary({ f }: { f: LiveForecast }) {
  return (
    <div className="space-y-2 text-sm">
      {f.award ? (
        <p>
          Award expected around <b>{f.award.date}</b> (in about {f.award.medianDays} days); 1 in 10 later than {f.award.p90Date}.
          Chance within 30 days {Math.round(f.award.within30 * 100)}%, within 90 days {Math.round(f.award.within90 * 100)}%.
          <span className="text-xs text-muted"> Based on {f.award.basis}.</span>
        </p>
      ) : f.stages.some((s) => s.stage === "bidding" && s.status === "done") ? null : (
        <p className="text-muted">No award forecast.</p>
      )}
      {f.contractEnd && <p>Contract expected to end around <b>{f.contractEnd}</b>.</p>}
      {f.warnings.length > 0 && (
        <ul className="space-y-1">
          {f.warnings.map((w, i) => (
            <li key={i} className="rounded-md bg-risk-medium-soft px-2 py-1 text-xs text-risk-medium">⚠ {w.text}</li>
          ))}
        </ul>
      )}
      {f.caveats.map((c, i) => <p key={i} className="text-xs text-muted">{c}</p>)}
      <p className="text-xs text-muted">A forecast, not a record: it is redone when new notices arrive, and real dates replace it.</p>
    </div>
  );
}
