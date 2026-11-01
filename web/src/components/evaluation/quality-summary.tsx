"use client";

import type { EvaluationResponse } from "@/lib/api/types";
import { localTime, pct, ratio } from "./measures";

interface Row { label: string; value: string; detail: string; when?: string }

/** The headline numbers of the evaluation in plain words: whether search finds the right passages, whether answers are
 * backed by their sources, whether questions the reports cannot answer are refused, and how the forecast compares with
 * the simple median. Each from the latest run that measured it. */
export function QualitySummary({ data }: { data: EvaluationResponse }) {
  const runs = [...data.quality].reverse();
  const search = runs.find((r) => r.hybrid_p5 != null);
  const full = runs.find((r) => r.answerable);
  const model = data.models.retrains.at(-1);
  const mae = model?.metrics.days_p50_mae;
  const auc = model?.metrics.over_180_auc;
  const rows: Row[] = [];
  if (search) rows.push({
    label: "Search finds the right passages",
    value: pct(search.hybrid_p5),
    detail: `Of the top 5 passages for a question, ${pct(search.hybrid_p5)} are relevant on average; the top 10 hold ${pct(search.hybrid_r10)} of all relevant passages known (${search.judged_pairs ?? "?"} question–passage pairs judged).`,
    when: search.time,
  });
  if (full) {
    rows.push({
      label: "Answers are backed by their sources",
      value: pct(ratio(full.supported_sentences, full.sentences)),
      detail: `${full.supported_sentences} of ${full.sentences} answer sentences are supported by the passages they cite${full.supported_independent != null ? `; ${full.supported_independent} by a second, independent model` : ""}.`,
      when: full.time,
    });
    rows.push({
      label: "Questions the reports cannot answer are refused",
      value: `${full.refused_traps}/${full.traps}`,
      detail: `Trap questions with no answer in the reports were refused instead of guessed; ${full.answered} of ${full.answerable} answerable questions were answered.`,
      when: full.time,
    });
  }
  if (mae) rows.push({
    label: "Forecast error against the simple median",
    value: `${Math.round(mae[0])} days`,
    detail: `Typical error of the tender-to-award forecast is ${Math.round(mae[0])} days, against ${Math.round(mae[1])} for the median of comparable packages`
      + `${auc ? `; the risk of more than 180 days ranks packages with AUC ${auc[0].toFixed(2)} (median-based: ${auc[1].toFixed(2)})` : ""}. Measured on ${model?.n ?? "?"} packages from ${model?.projects ?? "?"} projects, the projects held out in turn.`,
    when: model?.trained_at,
  });
  if (!rows.length) return <p className="text-sm text-ink-muted">Nothing measured yet.</p>;
  return (
    <dl className="divide-y divide-line border-y border-line">
      {rows.map((r) => (
        <div key={r.label} className="grid gap-x-8 gap-y-1 py-5 sm:grid-cols-[minmax(0,16rem)_7rem_minmax(0,1fr)] sm:items-baseline">
          <dt className="font-semibold">{r.label}</dt>
          <dd className="font-mono text-2xl text-brand-strong">{r.value}</dd>
          <dd className="text-sm text-ink-muted">
            {r.detail}
            {r.when && <span className="block text-xs">Measured {localTime(r.when.includes("UTC") ? r.when : toRunTime(r.when))}.</span>}
          </dd>
        </div>
      ))}
    </dl>
  );
}

/** "2026-10-26T03:48:02+00:00" as a run time ("2026-10-26 03:48 UTC"), so localTime reads it like the others. */
const toRunTime = (iso: string) => `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;

