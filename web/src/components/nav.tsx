"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api/client";
import type { Role } from "@/lib/api/types";
import { useAuth } from "./auth";

// Planner pages are for planners (and reviewers, who also read Evaluation); an admin sees only the admin pages.
const NAV: { href: string; label: string; roles: Role[] }[] = [
  { href: "/", label: "Overview", roles: ["planner", "reviewer"] },
  { href: "/plan", label: "Plan a project", roles: ["planner", "reviewer"] },
  { href: "/ask", label: "Ask the evidence", roles: ["planner", "reviewer"] },
  { href: "/insights", label: "Insights", roles: ["planner", "reviewer"] },
  { href: "/documents", label: "Documents", roles: ["planner", "reviewer"] },
  { href: "/pipeline", label: "Pipeline", roles: ["admin"] },
  { href: "/evaluation", label: "Evaluation", roles: ["reviewer", "admin"] },
  { href: "/config", label: "Settings", roles: ["admin"] },
];

const on = (path: string, href: string) => (href === "/" ? path === "/" : path.startsWith(href));

/** Navigation by role: planners see the planner app, reviewers also Evaluation, admins only Pipeline, Evaluation and Settings; the user and sign-out on the right. */
export function Nav() {
  const { user, refresh } = useAuth();
  const path = usePathname();
  if (!user) return null;
  async function signOut() {
    await api.logout().catch(() => null);
    await refresh();
  }
  return (
    <>
      <nav className="flex flex-wrap gap-1 text-sm">
        {NAV.filter((n) => n.roles.includes(user.role)).map((n) => (
          <Link key={n.href} href={n.href} aria-current={on(path, n.href) ? "page" : undefined}
            className={`rounded-md px-3 py-1.5 ${on(path, n.href) ? "bg-brand-soft text-brand" : "text-ink-muted hover:bg-subtle hover:text-foreground"}`}>
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2.5">
        <span className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-brand-strong to-brand-2 text-xs font-semibold uppercase text-[#f1f4ff]" aria-hidden>
          {user.username.slice(0, 2)}
        </span>
        <span className="leading-tight">
          <span className="block text-sm font-medium">{user.username}</span>
          <span className="block text-[11px] capitalize text-ink-muted">{user.role}</span>
        </span>
        {user.mode === "local" && (
          <button className="ml-1 inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs text-ink-muted transition hover:bg-subtle hover:text-foreground" onClick={signOut}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M6 2.5H3.5v11H6M10 5l3 3-3 3M13 8H6.5" /></svg>
            Sign out
          </button>
        )}
      </div>
    </>
  );
}
