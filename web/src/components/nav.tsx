"use client";

import Link from "next/link";
import { api } from "@/lib/api/client";
import type { Role } from "@/lib/api/types";
import { hasRole, useAuth } from "./auth";

const NAV: { href: string; label: string; role: Role }[] = [
  { href: "/", label: "Overview", role: "planner" },
  { href: "/assess", label: "Assess a package", role: "planner" },
  { href: "/ask", label: "Ask the evidence", role: "planner" },
  { href: "/insights", label: "Insights", role: "planner" },
  { href: "/pipeline", label: "Pipeline", role: "admin" },
  { href: "/evaluation", label: "Evaluation", role: "reviewer" },
  { href: "/config", label: "Settings", role: "admin" },
];

/** Navigation by role: planners see the planner app, reviewers also Evaluation, admins also the pipeline pages and Settings; the user and sign-out on the right. */
export function Nav() {
  const { user, refresh } = useAuth();
  if (!user) return null;
  async function signOut() {
    await api.logout().catch(() => null);
    await refresh();
  }
  return (
    <>
      <nav className="flex gap-1 text-sm">
        {NAV.filter((n) => hasRole(user.role, n.role)).map((n) => (
          <Link key={n.href} href={n.href} className="rounded-md px-3 py-1.5 text-ink-muted hover:bg-subtle hover:text-foreground">
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-3 text-xs text-ink-muted">
        <span>
          {user.username} · {user.role}
        </span>
        {user.mode === "local" && (
          <button className="underline" onClick={signOut}>
            Sign out
          </button>
        )}
      </div>
    </>
  );
}
