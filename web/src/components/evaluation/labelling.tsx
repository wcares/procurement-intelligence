"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { LabellingQueue } from "@/lib/api/types";

/** Checks a person makes so the measures can be trusted: confirm the relevance judge's labels, decide sentences the two
 * answer judges disagree on, and add questions users had trouble with to the evaluation set. */
export function Labelling() {
  const [q, setQ] = useState<LabellingQueue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    api.labelling().then(setQ).catch((e) => setError((e as Error).message));
  }, []);
  const apply = (p: Promise<LabellingQueue>) => p.then(setQ).catch((e) => setError((e as Error).message));

  async function add(question: string, answerable: boolean) {
    const r = await api.addEvalQuestion(question, answerable).catch((e) => ({ error: (e as Error).message }));
    if ("error" in r) return setNote(r.error);
    setNote(`Added as ${r.added.id}; ${answerable ? "its passages are judged on the next evaluation run" : "a trap the system must refuse"}.`);
    setQ(r);
  }

  if (error) return <p className="text-sm text-risk-high">{error}</p>;
  if (!q) return <p className="text-sm text-muted">Loading…</p>;
  const ag = q.judge.agreement;
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold">Relevance judge</h3>
        <p className="mb-2 text-xs text-muted">
          Search precision and recall are measured against labels a model gave. Is the passage relevant to the question?
          {ag.labelled > 0 ? ` You agreed with the judge on ${ag.agree} of ${ag.labelled}.` : " No labels yet."}
          {" "}Earlier hand check: 28 of 30 (eval/judge_check.md).
        </p>
        {q.judge.items.length === 0 ? <p className="text-xs text-muted">Nothing left to check.</p> : (
          <ul className="space-y-2">
            {q.judge.items.slice(0, 3).map((it) => (
              <li key={it.qid + it.chunkId} className="rounded-xl border border-line bg-surface p-3 text-sm">
                <p className="text-xs text-muted">{it.qid} · {it.question}</p>
                <blockquote className="my-2 border-l-2 border-line pl-3 text-xs">{it.passage ?? "(passage no longer in the index)"}</blockquote>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-muted">Judge: {it.judge ? "relevant" : "not relevant"}. You:</span>
                  <button className="rounded-md border border-line px-2 py-1" onClick={() => apply(api.labelJudgment(it.qid, it.chunkId, true))}>relevant</button>
                  <button className="rounded-md border border-line px-2 py-1" onClick={() => apply(api.labelJudgment(it.qid, it.chunkId, false))}>not relevant</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold">Sentence support: the judges disagree</h3>
        <p className="mb-2 text-xs text-muted">
          In the latest full run the answer model and the independent judge disagreed on {q.sentences.disagreements} of{" "}
          {q.sentences.sentences} sentences. Do the cited passages support the sentence?
          {q.sentences.decided.labelled > 0 && ` So far you sided with the answer model ${q.sentences.decided.answerModel} times and with the independent judge ${q.sentences.decided.independent} times.`}
        </p>
        {q.sentences.items.length === 0 ? <p className="text-xs text-muted">Nothing left to decide.</p> : (
          <ul className="space-y-2">
            {q.sentences.items.slice(0, 3).map((it) => (
              <li key={it.key} className="rounded-xl border border-line bg-surface p-3 text-sm">
                <p className="font-medium">{it.sentence}</p>
                {Object.entries(it.passages).map(([id, text]) => (
                  <blockquote key={id} className="my-2 border-l-2 border-line pl-3 text-xs"><span className="font-mono text-muted">{id}</span> {text}</blockquote>
                ))}
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-muted">Answer model: {it.answerModel ? "supported" : "not"} · independent judge: {it.independent ? "supported" : "not"}. You:</span>
                  <button className="rounded-md border border-line px-2 py-1" onClick={() => apply(api.labelSentence(it.key, true))}>supported</button>
                  <button className="rounded-md border border-line px-2 py-1" onClick={() => apply(api.labelSentence(it.key, false))}>not supported</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold">Questions from users</h3>
        <p className="mb-2 text-xs text-muted">Refused or rated not useful. Add one to the evaluation set as answerable (the reports should answer it) or as a trap (the system should refuse it).</p>
        {note && <p className="mb-2 text-xs text-muted">{note}</p>}
        {q.questions.length === 0 ? <p className="text-xs text-muted">None yet.</p> : (
          <ul className="divide-y divide-line rounded-xl border border-line bg-surface text-sm">
            {q.questions.map((it) => (
              <li key={it.kind + it.question} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2">
                <span className="min-w-0 flex-1 basis-64">{it.question}</span>
                <span className="text-xs text-muted">{it.kind === "refused_question" ? "refused" : "not useful"} · {it.responses}×{it.comments.length ? ` · “${it.comments[0]}”` : ""}</span>
                {it.inSet ? <span className="text-xs text-muted">in the set</span> : (
                  <span className="flex gap-2 text-xs">
                    <button className="underline" onClick={() => add(it.question, true)}>add as answerable</button>
                    <button className="underline" onClick={() => add(it.question, false)}>add as trap</button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
