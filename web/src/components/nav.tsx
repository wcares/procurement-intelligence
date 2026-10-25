"use client";

import Link from "next/link";
import { api } from "@/lib/api/client";
import { useAuth } from "./auth";

const NAV = [
  { href: "/", label: "Overview", admin: false },
  { href: "/assess", label: "Assess a package", admin: false },
  { href: "/ask", label: "Ask the evidence", admin: false },
  { href: "/config", label: "Settings", admin: true },
] as const;

/** Navigation by role: planners see the planner app, admins also Settings; the user and sign-out on the right. */
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
        {NAV.filter((n) => !n.admin || user.role === "admin").map((n) => (
          <Link key={n.href} href={n.href} className="rounded-md px-3 py-1.5 text-muted hover:bg-subtle hover:text-foreground">
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-3 text-xs text-muted">
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
