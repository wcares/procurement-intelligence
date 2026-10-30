"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, setSignedIn, SIGNED_OUT } from "@/lib/api/client";
import type { AuthUser, Role } from "@/lib/api/types";

const AuthContext = createContext<{ user: AuthUser | null; refresh: () => Promise<AuthUser | null> }>({ user: null, refresh: async () => null });

export const useAuth = () => useContext(AuthContext);

const PUBLIC_PAGES = ["/login", "/data-handling"]; // readable without signing in
// The planner app: an admin account is for running the platform and does not use it, so it is sent to its own home.
const PLANNER_PAGES = ["/", "/assess", "/plan", "/ask", "/insights", "/documents", "/package"];
export const ADMIN_HOME = "/pipeline";

// What a page needs; a page not listed is open to every signed-in role.
const PAGE_ROLE: [string, Role][] = [["/pipeline", "admin"], ["/config", "admin"], ["/evaluation", "reviewer"]];

/** Where to go after signing in: the page asked for when this role may use it, otherwise the role's own home. A session that
 * ended on an admin page must not land a planner on "this page needs the admin role". */
export function landingFor(next: string | null, role: Role): string {
  const home = role === "admin" ? ADMIN_HOME : "/";
  if (!next || !next.startsWith("/") || next.startsWith("//")) return home;
  const needed = PAGE_ROLE.find(([p]) => next === p || next.startsWith(`${p}/`))?.[1];
  if (needed && !hasRole(role, needed)) return home;
  if (role === "admin" && PLANNER_PAGES.includes(next.split("?")[0])) return home;
  return next;
}

/** Loads the signed-in user; any page but /login stays hidden until there is one, and a visitor without a session is
 * sent to /login. */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checked, setChecked] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  const refresh = async () => {
    const u = await api.me().catch(() => null);
    setUser(u);
    setChecked(true);
    return u;
  };

  useEffect(() => {
    let live = true;
    api.me().catch(() => null).then((u) => {
      if (!live) return;
      setUser(u);
      setChecked(true);
    });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    setSignedIn(Boolean(user));
  }, [user]);

  useEffect(() => {
    const onSignedOut = () => {
      setUser(null);
      setChecked(true);
    };
    window.addEventListener(SIGNED_OUT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT, onSignedOut);
  }, []);

  useEffect(() => {
    if (checked && !user && !PUBLIC_PAGES.includes(pathname)) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [checked, user, pathname, router]);

  useEffect(() => {
    if (user?.role === "admin" && PLANNER_PAGES.includes(pathname)) router.replace(ADMIN_HOME);
  }, [user, pathname, router]);

  // The page is rendered but hidden until the session is known (Next validates every rendered segment); the backend
  // checks the session on every call, so a hidden page without one gets 401s and the visitor is sent to /login.
  const ready = PUBLIC_PAGES.includes(pathname) || Boolean(checked && user && !(user.role === "admin" && PLANNER_PAGES.includes(pathname)));
  return (
    <AuthContext.Provider value={{ user, refresh }}>
      <div hidden={!ready} className="flex flex-1 flex-col">
        {children}
      </div>
    </AuthContext.Provider>
  );
}

const RANK: Record<Role, number> = { planner: 0, reviewer: 1, admin: 2 };

/** Whether `role` may use what needs `needed` (planner < reviewer < admin), as the backend decides. */
export function hasRole(role: Role | undefined, needed: Role): boolean {
  return role !== undefined && RANK[role] >= RANK[needed];
}

/** Content only a role (or one above it) may see (the backend refuses the calls anyway). */
export function RoleOnly({ role, children }: { role: Role; children: React.ReactNode }) {
  const { user } = useAuth();
  if (hasRole(user?.role, role)) return <>{children}</>;
  return <p className="text-sm text-ink-muted">This page needs the {role} role.</p>;
}

/** Content only an admin may see. */
export function AdminOnly({ children }: { children: React.ReactNode }) {
  return <RoleOnly role="admin">{children}</RoleOnly>;
}
