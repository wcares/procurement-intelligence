"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api/client";
import type { Role } from "@/lib/api/types";
import { useAuth } from "./auth";

// Planner pages are for planners (and reviewers, who also read Evaluation); an admin sees only the admin pages.
const NAV: { href: string; label: string; roles: Role[] }[] = [
  { href: "/plan", label: "Planning workspace", roles: ["planner", "reviewer"] },
  { href: "/insights", label: "Insights", roles: ["planner", "reviewer"] },
  { href: "/documents", label: "Documents", roles: ["planner", "reviewer"] },
  { href: "/pipeline", label: "Pipeline", roles: ["admin"] },
  { href: "/evaluation", label: "Evaluation", roles: ["reviewer", "admin"] },
  { href: "/config", label: "Settings", roles: ["admin"] },
];

const on = (path: string, href: string) => path.startsWith(href);

/** The header: the product name on the left, the pages for the signed-in role in the middle (planners see the planner app,
 * reviewers also Evaluation, admins only Pipeline, Evaluation and Settings), the user's menu on the right. */
export function HeaderBar() {
  const { user, refresh } = useAuth();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!menu.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  async function signOut() {
    await api.logout().catch(() => null);
    setOpen(false);
    await refresh();
  }
  return (
    <div className="mx-auto flex max-w-[1800px] flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 md:grid md:grid-cols-[1fr_auto_1fr] lg:px-8">
      <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
        <span className="grid size-7 place-items-center rounded-lg bg-gradient-to-br from-brand-strong to-teal-500 text-white shadow-[0_2px_10px_rgba(74,116,214,0.25)]" aria-hidden>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
            <path d="M2.5 11V5l5.5-3 5.5 3v6L8 14z" />
            <path d="M8 2v12M2.5 5L8 8l5.5-3" />
          </svg>
        </span>
        Procurement Intelligence
      </Link>
      {user && (
        <>
          <nav className="order-last flex w-full flex-wrap justify-center gap-1 text-sm md:order-none md:w-auto">
            {NAV.filter((n) => n.roles.includes(user.role)).map((n) => (
              <Link key={n.href} href={n.href} aria-current={on(path, n.href) ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 ${on(path, n.href) ? "bg-brand-soft text-brand" : "text-ink-muted hover:bg-subtle hover:text-foreground"}`}>
                {n.label}
              </Link>
            ))}
          </nav>
          <div ref={menu} className="relative justify-self-end">
            <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}
              className="flex items-center gap-2.5 rounded-xl py-1 pl-1 pr-2 transition hover:bg-subtle">
              <span className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-brand-strong to-brand-2 text-xs font-semibold uppercase text-[#f1f4ff]" aria-hidden>
                {user.username.slice(0, 2)}
              </span>
              <span className="text-left leading-tight">
                <span className="block text-sm font-medium">{user.username}</span>
                <span className="block text-[11px] capitalize text-ink-muted">{user.role}</span>
              </span>
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={`text-ink-muted transition ${open ? "rotate-180" : ""}`} aria-hidden><path d="M2.5 4.5L6 8l3.5-3.5" /></svg>
            </button>
            {open && (
              <div role="menu" className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-line bg-surface p-1.5 shadow-2xl">
                <div className="px-3 py-2 text-xs text-ink-muted">Signed in as <span className="font-medium text-foreground">{user.username}</span><br /><span className="capitalize">{user.role}</span></div>
                {user.mode === "local" ? (
                  <button role="menuitem" onClick={signOut} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-foreground transition hover:bg-subtle">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M6 2.5H3.5v11H6M10 5l3 3-3 3M13 8H6.5" /></svg>
                    Sign out
                  </button>
                ) : <p className="px-3 py-2 text-xs text-ink-muted">Signed in through your organisation.</p>}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
