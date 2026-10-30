"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import { useAuth } from "@/components/auth";

const field = "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand";

export function LoginView() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.login(username, password);
      if ("error" in r) return setError(r.error);
      await refresh();
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-surface p-6">
      <label className="block text-sm">
        Username
        <input className={field} autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
      </label>
      <label className="block text-sm">
        Password
        <input className={field} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
      </label>
      {error && <p className="text-sm text-risk-high">{error}</p>}
      <button type="submit" disabled={busy} className="w-full rounded-md bg-brand px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <p className="text-center text-xs text-ink-muted">
        <Link className="underline" href="/data-handling">How your data is handled</Link>
      </p>
    </form>
  );
}
