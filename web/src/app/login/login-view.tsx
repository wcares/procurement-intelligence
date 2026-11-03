"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api/client";
import { landingFor, useAuth } from "@/components/auth";

export const field = "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-brand";

const PORTAL = {
  planner: { title: "Planner sign-in", lead: "For planners: Assess, the planning workspace, Ask and Insights." },
  admin: { title: "Administrator sign-in", lead: "For running the platform: the data pipeline, models, accounts and settings." },
};

/** A sign-in page: each admits only its roles (the backend refuses the others, procintel.auth.service.PORTALS) and
 * points to the other one. */
export function SignInPage({ portal }: { portal: "planner" | "admin" }) {
  const other = portal === "planner" ? "admin" : "planner";
  return (
    <div className="mx-auto mt-10 max-w-sm space-y-6">
      <div>
        <Link href="/welcome" className="text-xs text-ink-muted underline underline-offset-2">← Procurement Intelligence</Link>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">{PORTAL[portal].title}</h1>
        <p className="mt-1 text-sm text-ink-muted">{PORTAL[portal].lead}</p>
      </div>
      <LoginView portal={portal} />
      <div className="space-y-1 text-center text-sm text-ink-muted">
        {portal === "planner" && (
          <p>No account yet? <Link href="/signup" className="font-medium text-brand underline underline-offset-2">Request access</Link></p>
        )}
        <p>
          {portal === "planner" ? "Running the platform? " : "Planning procurement? "}
          <Link href={`/login/${other}`} className="underline underline-offset-2">{PORTAL[other].title}</Link>
        </p>
      </div>
    </div>
  );
}

export function LoginView({ portal }: { portal: "planner" | "admin" }) {
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
      const r = await api.login(username, password, portal);
      if ("error" in r) return setError(r.error);
      const user = await refresh();
      router.replace(landingFor(new URLSearchParams(window.location.search).get("next"), user?.role ?? "planner"));
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
      <button type="submit" disabled={busy} className="w-full rounded-md bg-brand px-3 py-2 text-sm font-medium text-on-brand disabled:opacity-50">
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <p className="text-center text-xs text-ink-muted">
        <Link className="underline" href="/data-handling">How your data is handled</Link>
      </p>
    </form>
  );
}
