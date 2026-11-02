"use client";

import { useEffect, useState } from "react";
import { KeyRound, Play } from "lucide-react";
import { api } from "@/lib/api/client";
import type { ConfigProfile, ConfigSetting, ModelKeyStatus, ModelTestResult } from "@/lib/api/types";

const ROLES: { role: string; label: string; model: string; base: string }[] = [
  { role: "llm", label: "Answer model", model: "llm_model", base: "llm_api_base" },
  { role: "judge", label: "Second checking model", model: "judge_model", base: "judge_api_base" },
  { role: "batch", label: "Model for background work", model: "batch_model", base: "batch_api_base" },
];

/** Each model as it is set now, its API key (write-only: set, replace or remove; the page only learns whether one is
 * set) and a test that sends it one short question. A change of model name or address below applies to the next
 * request; so does a key set here. */
export function ModelAccess({ settings, onSettings }: { settings: ConfigSetting[]; onSettings: (s: ConfigSetting[]) => void }) {
  const [keys, setKeys] = useState<Record<string, ModelKeyStatus> | null>(null);
  const [profiles, setProfiles] = useState<ConfigProfile[]>([]);
  const [switching, setSwitching] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    api.modelKeys().then((r) => setKeys(r.keys)).catch(() => setKeys({}));
    api.profiles().then((r) => setProfiles(r.profiles)).catch(() => setProfiles([]));
  }, []);
  // saved profiles that set an answer model: one click switches name, address and options together
  const switches = profiles.filter((p) => p.values.llm_model);
  async function use(p: ConfigProfile) {
    setSwitching(p.name);
    try {
      const r = await api.applyProfile(p.name, true);
      onSettings(r.settings);
      setNote(`Now using ${p.values.llm_model}; the next question goes to it. Kept after a restart.`);
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setSwitching(null);
    }
  }
  const value = (k: string) => String(settings.find((s) => s.key === k)?.value ?? "");
  return (
    <section className="space-y-4 rounded-lg border border-line bg-surface p-5">
      <div>
        <p className="font-semibold">Model access</p>
        <p className="mt-1 text-sm text-ink-muted">
          Switch a model by changing its name (and address, for a server of your own) below; it applies to the next request,
          without a restart. A local model needs only its address; a hosted one (Claude, OpenAI and others) needs only
          its name, such as <span className="font-mono">anthropic/claude-sonnet-5-5</span>, and an API key set here. Keys are
          stored on the server and never shown again.
        </p>
      </div>
      {switches.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">Switch the answer model</p>
          <div className="flex flex-wrap gap-2">
            {switches.map((p) => {
              const active = value("llm_model") === p.values.llm_model && value("llm_api_base") === String(p.values.llm_api_base ?? "");
              return (
                <button key={p.name} type="button" disabled={active || switching !== null} onClick={() => void use(p)}
                  className={`rounded-md border px-3 py-1.5 text-sm ${active ? "border-brand bg-brand-soft font-medium" : "border-line"} disabled:cursor-default`}>
                  {switching === p.name ? "Switching…" : p.name}{active ? " (in use)" : ""}
                </button>
              );
            })}
          </div>
          {note && <p className="text-xs text-ink-muted">{note}</p>}
        </div>
      )}
      <div className="divide-y divide-line">
        {ROLES.map((r) => (
          <RoleRow key={r.role} label={r.label} role={r.role} model={value(r.model)} base={value(r.base)}
            status={keys?.[r.role]} onKeys={setKeys} />
        ))}
      </div>
    </section>
  );
}

function RoleRow({ label, role, model, base, status, onKeys }: {
  label: string; role: string; model: string; base: string; status?: ModelKeyStatus;
  onKeys: (k: Record<string, ModelKeyStatus>) => void;
}) {
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [test, setTest] = useState<ModelTestResult | "running" | null>(null);

  async function save() {
    const r = await api.setModelKey(role, draft);
    if ("error" in r) return setNote(r.error);
    onKeys(r.keys);
    setDraft("");
    setNote("Key saved; the next request uses it.");
  }
  async function remove() {
    const r = await api.removeModelKey(role).catch((e: Error) => ({ error: e.message }));
    if ("error" in r) return setNote(r.error as string);
    onKeys(r.keys);
    setNote(r.keys[role]?.set ? "Page key removed; the key from the environment applies again." : "Key removed.");
  }
  async function run() {
    setTest("running");
    setTest(await api.testModel(role).catch((e: Error) => ({ ok: false, model: model || null, error: e.message })));
  }

  const keyText = !status ? "…" : !status.set ? "no key" : status.from === "page" ? "key set on this page" : "key from the environment";
  return (
    <div className="space-y-2 py-4 first:pt-2 last:pb-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-medium">{label}</span>
        <span className="font-mono text-sm">{model || (role === "batch" ? "(the answer model)" : "(not set)")}</span>
        <span className="text-xs text-ink-muted">{base ? `at ${base}` : model ? "provider's own address" : ""}</span>
        <span className={`ml-auto inline-flex items-center gap-1 text-xs ${status?.set ? "text-risk-low" : "text-ink-muted"}`}>
          <KeyRound size={13} aria-hidden /> {keyText}
        </span>
      </div>
      <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <input type="password" autoComplete="off" value={draft} onChange={(e) => setDraft(e.target.value)}
          placeholder={status?.set ? "Paste a new key to replace it" : "Paste an API key"} aria-label={`API key for the ${label.toLowerCase()}`}
          className="w-full max-w-xs rounded-md border border-line bg-surface px-3 py-1.5 font-mono text-sm outline-none focus:border-brand-2" />
        <button type="submit" disabled={draft.trim().length < 8} className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium disabled:opacity-40">
          {status?.set ? "Replace key" : "Save key"}
        </button>
        {status?.from === "page" && <button type="button" onClick={() => void remove()} className="rounded-md border border-line px-3 py-1.5 text-xs">Remove key</button>}
        <button type="button" onClick={() => void run()} disabled={test === "running"}
          className="inline-flex items-center gap-1 rounded-md border border-line px-3 py-1.5 text-xs disabled:opacity-50">
          <Play size={12} aria-hidden /> {test === "running" ? "Testing…" : "Test this model"}
        </button>
      </form>
      {note && <p className="text-xs text-ink-muted">{note}</p>}
      {test && test !== "running" && (
        test.ok ? (
          <p className="text-sm"><span className="text-risk-low">Works:</span> {test.model} answered in {test.seconds} s:{" "}
            <span className="italic text-ink-muted">“{test.reply}”</span></p>
        ) : (
          <p className="text-sm text-risk-high">Not working{test.model ? ` (${test.model})` : ""}: {test.error}</p>
        )
      )}
    </div>
  );
}
