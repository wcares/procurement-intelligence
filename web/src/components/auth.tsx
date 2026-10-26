"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, SIGNED_OUT } from "@/lib/api/client";
import type { AuthUser, Role } from "@/lib/api/types";

const AuthContext = createContext<{ user: AuthUser | null; refresh: () => Promise<void> }>({ user: null, refresh: async () => {} });

export const useAuth = () => useContext(AuthContext);

const PUBLIC_PAGES = ["/login", "/data-handling"]; // readable without signing in

/** Loads the signed-in user; any page but /login stays hidden until there is one, and a visitor without a session is
 * sent to /login. */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checked, setChecked] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  const refresh = async () => {
    setUser(await api.me().catch(() => null));
    setChecked(true);
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

  // The page is rendered but hidden until the session is known (Next validates every rendered segment); the backend
  // checks the session on every call, so a hidden page without one gets 401s and the visitor is sent to /login.
  const ready = PUBLIC_PAGES.includes(pathname) || Boolean(checked && user);
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
