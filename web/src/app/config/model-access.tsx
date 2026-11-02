"use client";

import { useEffect, useState } from "react";
import { KeyRound, Play, X } from "lucide-react";
import { api } from "@/lib/api/client";
import type { ConfigSetting, ModelProfile, ModelTestResult, ProviderKeyStatus } from "@/lib/api/types";

const ROLES: { role: string; label: string; model: string; base: string }[] = [
  { role: "llm", label: "Answer model", model: "llm_model", base: "llm_api_base" },
  { role: "judge", label: "Second checking model", model: "judge_model", base: "judge_api_base" },
  { role: "batch", label: "Model for background work", model: "batch_model", base: "batch_api_base" },
];

/** The provider whose saved key a model uses: its name's prefix, for a hosted model (no address); as on the server. */
const providerOf = (model: string, base: string, providers: ProviderKeyStatus[]) =>
  !model || base || !model.includes("/") ? null : providers.find((p) => p.provider === model.split("/")[0].toLowerCase()) ?? null;

/** Switch the answer model in one click (saved model profiles), save each provider's API key once, and test each model.
 * A profile holds only the model (name, address, options), so a switch changes nothing else; a hosted model uses its
 * provider's saved key, a server of your own needs none. Keys are kept on the server and never shown again. */
export function ModelAccess({ settings, onSettings }: { settings: ConfigSetting[]; onSettings: (s: ConfigSetting[]) => void }) {
  const [providers, setProviders] = useState<ProviderKeyStatus[]>([]);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [name, setName] = useState("");
  useEffect(() => {
    api.providerKeys().then((r) => setProviders(r.providers)).catch(() => setProviders([]));
    api.modelProfiles().then((r) => setProfiles(r.profiles)).catch(() => setProfiles([]));
  }, []);
  const value = (k: string) => String(settings.find((s) => s.key === k)?.value ?? "");

  async function use(p: ModelProfile) {
    setBusy(p.name);
    try {
      const r = await api.applyModelProfile(p.name);
      onSettings(r.settings);
      setProfiles(r.profiles);
      const prov = providers.find((x) => x.provider === p.provider);
      setNote(`Now using ${p.model}; the next question goes to it.${prov && !prov.set ? ` Save a ${prov.label} key below first.` : ""}`);
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(null);
    }
  }
  async function saveProfile() {
    try {
      setProfiles((await api.saveModelProfile(name.trim())).profiles);
      setNote(`Saved "${name.trim()}": the answer model as it is set now.`);
      setName("");
    } catch (e) {
      setNote((e as Error).message);
    }
  }
  async function removeProfile(p: ModelProfile) {
    setProfiles((await api.removeModelProfile(p.name).catch(() => ({ profiles }))).profiles);
  }

  return (
    <section className="space-y-5 rounded-lg border border-line bg-surface p-5">
      <div>
        <p className="font-semibold">Model access</p>
        <p className="mt-1 text-sm text-ink-muted">
          Switch the answer model with one click. A hosted model (Claude, OpenAI and others) uses its provider&apos;s key, saved
          once below; a server of your own (llama.cpp) needs none. A switch applies to the next request, without a restart,
          and changes nothing but the model.
        </p>
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium">Switch the answer model</p>
        <div className="flex flex-wrap gap-2">
          {profiles.length === 0 && <span className="text-sm text-ink-muted">No saved models yet: set one below and save it.</span>}
          {profiles.map((p) => (
            <span key={p.name} className={`inline-flex items-center rounded-md border text-sm ${p.active ? "border-brand bg-brand-soft" : "border-line"}`}>
              <button type="button" disabled={p.active || busy !== null} onClick={() => void use(p)} title={`${p.model}${p.api_base ? ` at ${p.api_base}` : ""}`}
                className={`px-3 py-1.5 ${p.active ? "font-medium" : ""} disabled:cursor-default`}>
                {busy === p.name ? "Switching…" : p.name}{p.active ? " (in use)" : ""}
              </button>
              {!p.active && (
                <button type="button" aria-label={`Remove ${p.name}`} onClick={() => void removeProfile(p)} className="px-1.5 text-ink-muted hover:text-risk-high">
                  <X size={13} aria-hidden />
                </button>
              )}
            </span>
          ))}
        </div>
        <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); void saveProfile(); }}>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Cloud: GPT-5"
            className="w-full max-w-xs rounded-md border border-line bg-surface px-3 py-1.5 text-sm outline-none focus:border-brand-2" />
          <button type="submit" disabled={!name.trim()} className="rounded-md border border-line px-3 py-1.5 text-xs disabled:opacity-40">
            Save the current answer model
          </button>
          <span className="text-xs text-ink-muted">(set its name, address and options in the cards below first)</span>
        </form>
        {note && <p className="text-xs text-ink-muted">{note}</p>}
      </div>

      <ProviderKeys providers={providers} onChange={setProviders} />

      <div className="divide-y divide-line border-t border-line">
        {ROLES.map((r) => (
          <RoleRow key={r.role} label={r.label} role={r.role} model={value(r.model)} base={value(r.base)}
            provider={providerOf(value(r.model) || (r.role === "batch" ? value("llm_model") : ""), r.role === "batch" && !value(r.model) ? value("llm_api_base") : value(r.base), providers)} />
        ))}
      </div>
    </section>
  );
}

function ProviderKeys({ providers, onChange }: { providers: ProviderKeyStatus[]; onChange: (p: ProviderKeyStatus[]) => void }) {
  const [provider, setProvider] = useState("anthropic");
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const saved = providers.filter((p) => p.set);
  async function save() {
    const r = await api.setProviderKey(provider, draft);
    if ("error" in r) return setNote(r.error);
    onChange(r.providers);
    setDraft("");
    setNote("Key saved: every model of this provider uses it from the next request.");
  }
  async function remove(p: string) {
    onChange((await api.removeProviderKey(p)).providers);
  }
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">Saved keys</p>
      <div className="flex flex-wrap gap-2 text-sm">
        {saved.length === 0 && <span className="text-ink-muted">None yet.</span>}
        {saved.map((p) => (
          <span key={p.provider} className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1">
            <KeyRound size={13} className="text-risk-low" aria-hidden /> {p.label}
            <button type="button" aria-label={`Remove the ${p.label} key`} onClick={() => void remove(p.provider)} className="text-ink-muted hover:text-risk-high">
              <X size={13} aria-hidden />
            </button>
          </span>
        ))}
      </div>
      <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <select value={provider} onChange={(e) => setProvider(e.target.value)} aria-label="Provider"
          className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm">
          {providers.map((p) => <option key={p.provider} value={p.provider}>{p.label}{p.set ? " (saved)" : ""}</option>)}
        </select>
        <input type="password" autoComplete="off" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Paste its API key"
          aria-label="API key" className="w-full max-w-xs rounded-md border border-line bg-surface px-3 py-1.5 font-mono text-sm outline-none focus:border-brand-2" />
        <button type="submit" disabled={draft.trim().length < 8} className="rounded-md bg-brand px-3 py-1.5 text-xs font-medium disabled:opacity-40">Save key</button>
      </form>
      {note && <p className="text-xs text-ink-muted">{note}</p>}
    </div>
  );
}

function RoleRow({ label, role, model, base, provider }: { label: string; role: string; model: string; base: string; provider: ProviderKeyStatus | null }) {
  const [test, setTest] = useState<ModelTestResult | "running" | null>(null);
  async function run() {
    setTest("running");
    setTest(await api.testModel(role).catch((e: Error) => ({ ok: false, model: model || null, error: e.message })));
  }
  const keyText = base || (!model && role !== "batch") ? (model || role === "batch" ? "your own server: no key needed" : "")
    : provider ? (provider.set ? `uses the saved ${provider.label} key` : `needs a ${provider.label} key (save it above)`) : "";
  return (
    <div className="space-y-2 py-4 last:pb-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-medium">{label}</span>
        <span className="font-mono text-sm">{model || (role === "batch" ? "(the answer model)" : "(not set)")}</span>
        <span className="text-xs text-ink-muted">{base ? `at ${base}` : model ? "provider's own address" : ""}</span>
        <span className={`ml-auto inline-flex items-center gap-1 text-xs ${provider && !provider.set && !base ? "text-risk-high" : "text-ink-muted"}`}>
          {keyText && <KeyRound size={13} aria-hidden />} {keyText}
        </span>
        <button type="button" onClick={() => void run()} disabled={test === "running"}
          className="inline-flex items-center gap-1 rounded-md border border-line px-3 py-1 text-xs disabled:opacity-50">
          <Play size={12} aria-hidden /> {test === "running" ? "Testing…" : "Test this model"}
        </button>
      </div>
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
