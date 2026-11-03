"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api/client";
import type { Role } from "@/lib/api/types";
import { ChartNoAxesGantt, ChevronDown, LogOut, Moon, Sun } from "lucide-react";
import { useAuth } from "./auth";

// Planner pages are for planners; an admin sees only the admin pages.
const NAV: { href: string; label: string; roles: Role[] }[] = [
  { href: "/plan", label: "Planning workspace", roles: ["planner"] },
  { href: "/insights", label: "Insights", roles: ["planner"] },
  { href: "/documents", label: "Documents", roles: ["planner"] },
  { href: "/pipeline", label: "Pipeline", roles: ["admin"] },
  { href: "/evaluation", label: "Quality", roles: ["admin"] },
  { href: "/config", label: "Settings", roles: ["admin"] },
];

const on = (path: string, href: string) => path.startsWith(href);

/** The header: the product name on the left, the pages for the signed-in role in the middle (planners see the planner app,
 * admins only Pipeline, Quality and Settings), the user's menu on the right. */
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
  const [dark, setDark] = useState(false);
  useEffect(() => {   // the theme chosen before, in this browser
    let saved: string | null = null;
    try { saved = localStorage.getItem("procintel.theme"); } catch { /* storage blocked */ }
    if (saved === "dark") { document.documentElement.dataset.theme = "dark"; setDark(true); } // eslint-disable-line react-hooks/set-state-in-effect
  }, []);
  function toggleTheme() {
    const next = !dark;
    document.documentElement.dataset.theme = next ? "dark" : "light";
    try { localStorage.setItem("procintel.theme", next ? "dark" : "light"); } catch { /* storage blocked */ }
    setDark(next);
  }
  async function signOut() {
    await api.logout().catch(() => null);
    setOpen(false);
    await refresh();
  }
  return (
    <div className="mx-auto grid h-14 max-w-[1400px] grid-cols-[1fr_auto_1fr] items-center gap-6 px-4 lg:px-8">
      <Link href="/" className="flex items-center gap-2.5 justify-self-start">
        <ChartNoAxesGantt size={20} strokeWidth={1.75} className="text-brand" aria-hidden />
        <span className="text-[15px] font-semibold text-brand-strong">Procurement Intelligence</span>
      </Link>
      {user ? (
        <>
          <nav className="flex h-full items-stretch gap-6 overflow-x-auto text-sm">
            {NAV.filter((n) => n.roles.includes(user.role)).map((n) => (
              <Link key={n.href} href={n.href} aria-current={on(path, n.href) ? "page" : undefined}
                className={`flex items-center border-b-2 whitespace-nowrap transition-colors ${on(path, n.href) ? "border-brand-2 font-semibold text-brand-strong" : "border-transparent text-ink-muted hover:text-foreground"}`}>
                {n.label}
              </Link>
            ))}
          </nav>
          <div ref={menu} className="relative justify-self-end">
            <button type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}
              className="flex items-center gap-2 rounded-md px-1.5 py-1 transition-colors hover:bg-subtle">
              <span className="grid size-7 place-items-center rounded-full bg-brand text-[11px] font-semibold uppercase text-on-brand" aria-hidden>
                {user.username.slice(0, 2)}
              </span>
              <span className="hidden text-left leading-tight sm:block">
                <span className="block text-sm">{user.username}</span>
                <span className="block text-[11px] capitalize text-ink-muted">{user.role}</span>
              </span>
              <ChevronDown size={14} className="text-ink-muted" aria-hidden />
            </button>
            {open && (
              <div role="menu" className="absolute right-0 z-30 mt-1 w-56 rounded-md border border-line bg-surface p-1 shadow-[0_2px_8px_rgba(0,0,0,0.1)]">
                <div className="px-3 py-2 text-xs text-ink-muted">Signed in as <span className="font-medium text-foreground">{user.username}</span> · <span className="capitalize">{user.role}</span></div>
                <button role="menuitem" onClick={toggleTheme} className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition-colors hover:bg-subtle">
                  {dark ? <Sun size={14} aria-hidden /> : <Moon size={14} aria-hidden />} {dark ? "Light theme" : "Dark theme"}
                </button>
                {user.mode === "local" ? (
                  <button role="menuitem" onClick={signOut} className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition-colors hover:bg-subtle">
                    <LogOut size={14} aria-hidden /> Sign out
                  </button>
                ) : <p className="px-3 py-2 text-xs text-ink-muted">Signed in through your organisation.</p>}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
