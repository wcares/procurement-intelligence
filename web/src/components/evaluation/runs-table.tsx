import type { EvalRun } from "@/lib/api/types";
import { localTime, MEASURES, pct } from "./measures";

/** Every run, newest first: the chart's numbers as text, plus time per answer and what changed before the run. */
export function RunsTable({ runs }: { runs: EvalRun[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="text-ink-muted">
          <tr>
            <th className="py-1 pr-2">Run</th>
            {MEASURES.map((m) => <th key={m.key} className="pr-2">{m.label}</th>)}
            <th className="pr-2">Median s / answer</th>
            <th>Changes before it</th>
          </tr>
        </thead>
        <tbody>
          {[...runs].reverse().map((r) => (
            <tr key={r.time} className="border-t border-line align-top">
              <td className="py-1 pr-2 whitespace-nowrap">{localTime(r.time)}</td>
              {MEASURES.map((m) => <td key={m.key} className="pr-2 tabular-nums">{pct(m.value(r))}</td>)}
              <td className="pr-2 tabular-nums">{r.median_seconds ?? "–"}</td>
              <td className="text-ink-muted">
                {(r.changesBefore ?? []).map((c) => `${c.what} (${c.detail})`).join("; ") || (r.note ?? "")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
