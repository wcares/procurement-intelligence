"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { PromptEvalSide, PromptInfo, PromptVersion } from "@/lib/api/types";

const side = (s: PromptEvalSide) =>
  `answered ${s.answered}/${s.answerable} · supported sentences ${s.supported_sentences}/${s.sentences} · refused traps ${s.refused_traps}/${s.traps} · median ${s.median_seconds ?? "–"} s`;

export function Prompts() {
  const [list, setList] = useState<PromptInfo[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api.prompts().then((r) => setList(r.prompts)).catch(() => setList(null));
  }, []);

  function edit(p: PromptInfo) {
    setOpen(open === p.name ? null : p.name);
    setDraft(p.versions.find((v) => v.active)?.text ?? "");
    setNote("");
    setMsg(null);
  }

  async function save(p: PromptInfo) {
    try {
      const r = await api.savePrompt(p.name, draft, note);
      setMsg(
        r.evaluationJob
          ? `Saved as version ${r.version}. It is compared with the active version on sample questions in the background; activate it once the result is in.`
          : `Saved as version ${r.version}. Nothing measures this prompt automatically: activate it when ready.`,
      );
      setList((await api.prompts()).prompts);
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  async function activate(p: PromptInfo, v: PromptVersion) {
    try {
      setList((await api.activatePrompt(p.name, v.version)).prompts);
      setMsg(`Version ${v.version} of ${p.label} is active from the next request.`);
    } catch (e) {
      setMsg((e as Error).message);
    }
  }

  if (!list) return null;
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Prompts</h2>
      <div className="space-y-2 rounded-xl border border-line bg-surface p-4">
        <p className="text-xs text-muted">
          What each model is told. An edit is saved as a new version; prompts used in answering are first compared with
          the active version on sample questions.
        </p>
        <ul className="divide-y divide-line text-sm">
          {list.map((p) => (
            <li key={p.name} className="py-2">
              <button className="flex w-full flex-wrap items-baseline gap-x-2 text-left" onClick={() => edit(p)}>
                <span className="font-medium">{p.label}</span>
                <span className="text-xs text-muted">version {p.active === 0 ? "default" : p.active} · {p.usedBy}</span>
              </button>
              {open === p.name && (
                <div className="mt-2 space-y-2">
                  <textarea className="h-40 w-full rounded-md border border-line bg-surface p-2 font-mono text-xs" value={draft} onChange={(e) => setDraft(e.target.value)} />
                  <div className="flex flex-wrap gap-2">
                    <input className="flex-1 rounded-md border border-line bg-surface px-2 py-1 text-xs" placeholder="What changed (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                    <button className="rounded-md border border-line px-2 py-1 text-xs" onClick={() => save(p)}>
                      Save as new version
                    </button>
                  </div>
                  {msg && <p className="text-xs text-muted">{msg}</p>}
                  <ul className="space-y-1 text-xs">
                    {p.versions.map((v) => (
                      <li key={v.version} className="flex flex-wrap items-baseline gap-x-2">
                        <span className="font-medium">{v.version === 0 ? "default" : `v${v.version}`}</span>
                        {v.active ? <span className="text-muted">active</span> : (
                          <button className="underline" onClick={() => activate(p, v)}>activate</button>
                        )}
                        {v.note && <span className="text-muted">{v.note}</span>}
                        {v.evaluation && (
                          <span className="w-full text-muted">
                            vs v{v.evaluation.versions.active}: {side(v.evaluation.candidate)} (active: {side(v.evaluation.active)})
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
