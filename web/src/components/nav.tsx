"use client";

import Link from "next/link";
import { api } from "@/lib/api/client";
import type { Role } from "@/lib/api/types";
import { useAuth } from "./auth";

// Planner pages are for planners (and reviewers, who also read Evaluation); an admin sees only the admin pages.
const NAV: { href: string; label: string; roles: Role[] }[] = [
  { href: "/", label: "Overview", roles: ["planner", "reviewer"] },
  { href: "/assess", label: "Assess a package", roles: ["planner", "reviewer"] },
  { href: "/plan", label: "Plan a project", roles: ["planner", "reviewer"] },
  { href: "/ask", label: "Ask the evidence", roles: ["planner", "reviewer"] },
  { href: "/insights", label: "Insights", roles: ["planner", "reviewer"] },
  { href: "/documents", label: "Documents", roles: ["planner", "reviewer"] },
  { href: "/pipeline", label: "Pipeline", roles: ["admin"] },
  { href: "/evaluation", label: "Evaluation", roles: ["reviewer", "admin"] },
  { href: "/config", label: "Settings", roles: ["admin"] },
];

/** Navigation by role: planners see the planner app, reviewers also Evaluation, admins only Pipeline, Evaluation and Settings; the user and sign-out on the right. */
export function Nav() {
  const { user, refresh } = useAuth();
  if (!user) return null;
  async function signOut() {
    await api.logout().catch(() => null);
    await refresh();
  }
  return (
    <>
      <nav className="flex flex-wrap gap-1 text-sm">
        {NAV.filter((n) => n.roles.includes(user.role)).map((n) => (
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
