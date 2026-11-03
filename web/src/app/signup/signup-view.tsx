"use client";

import Link from "next/link";
import { useState } from "react";
import { CircleCheck } from "lucide-react";
import { api } from "@/lib/api/client";
import { field } from "../login/login-view";

/** Request access: a planner account that works once an administrator approves it (Settings, Accounts). Nobody asks
 * for a role here; an administrator can change it when approving. */
export function SignUpView() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== repeat) return setError("the two passwords differ");
    setBusy(true);
    setError(null);
    try {
      const r = await api.signup(username.trim(), password);
      if ("error" in r) return setError(r.error);
      setSent(username.trim());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div className="space-y-3 rounded-xl border border-line bg-surface p-6 text-sm">
        <p className="flex items-center gap-2 font-medium text-risk-low"><CircleCheck size={16} aria-hidden /> Request sent</p>
        <p>
          An administrator will review the request for <span className="font-medium">{sent}</span>. Once it is approved,
          sign in on the planner sign-in with the password you chose.
        </p>
        <Link href="/login/planner" className="inline-block font-medium text-brand underline underline-offset-2">Planner sign-in</Link>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-surface p-6">
      <label className="block text-sm">
        Username
        <input className={field} autoComplete="username" maxLength={60} value={username} onChange={(e) => setUsername(e.target.value)} required />
      </label>
      <label className="block text-sm">
        Password <span className="text-ink-muted">(10 characters or more)</span>
        <input className={field} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      <label className="block text-sm">
        Password again
        <input className={field} type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} required />
      </label>
      {error && <p className="text-sm text-risk-high">{error}</p>}
      <button type="submit" disabled={busy} className="w-full rounded-md bg-brand px-3 py-2 text-sm font-medium text-on-brand disabled:opacity-50">
        {busy ? "Sending…" : "Request access"}
      </button>
      <p className="text-center text-xs text-ink-muted">
        <Link className="underline" href="/data-handling">How your data is handled</Link>
      </p>
    </form>
  );
}
