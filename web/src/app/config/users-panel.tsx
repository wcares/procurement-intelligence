"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Account } from "@/lib/api/types";
import { useAuth } from "@/components/auth";

const box = "rounded-md border border-line bg-surface px-2 py-1 text-xs";

/** Accounts and roles (admins). Passwords are set here or with `python -m procintel.auth`, never shown. */
export function Users() {
  const { user } = useAuth();
  const [list, setList] = useState<Account[] | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("planner");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    if (user?.mode === "local") api.users().then((r) => setList(r.users)).catch(() => setList(null));
  }, [user]);

  async function apply(r: { users: Account[] } | { error: string }, ok: string) {
    if ("error" in r) return setMsg(r.error);
    setList(r.users);
    setMsg(ok);
  }

  if (user?.mode !== "local" || !list) return null;
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-muted">Users</h2>
      <div className="space-y-3 rounded-xl border border-line bg-surface p-4 text-xs">
        <p className="text-ink-muted">Planners use Assess and Ask; admins also see Settings. A change signs the person out.</p>
        <table className="w-full text-left">
          <thead className="text-ink-muted"><tr><th>User</th><th>Role</th><th>Status</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {list.map((u) => (
              <tr key={u.username} className="border-t border-line">
                <td className="py-1 font-medium">{u.username}</td>
                <td>
                  <select className={box} value={u.role} disabled={u.username === user.username}
                    onChange={async (e) => apply(await api.updateUser(u.username, { role: e.target.value }), `${u.username} is now ${e.target.value}.`)}>
                    <option value="planner">planner</option>
                    <option value="reviewer">reviewer</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td>{u.active ? "active" : "disabled"}</td>
                <td>{u.lastLogin ? new Date(u.lastLogin).toLocaleString() : "never"}</td>
                <td className="text-right">
                  {u.username !== user.username && (
                    <button className="underline" onClick={async () => apply(await api.updateUser(u.username, { active: !u.active }), `${u.username} ${u.active ? "disabled" : "enabled"}.`)}>
                      {u.active ? "disable" : "enable"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <form className="flex flex-wrap gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            await apply(await api.createUser(name, password, role), `${name} added.`);
            setName("");
            setPassword("");
          }}>
          <input className={box} placeholder="username" value={name} onChange={(e) => setName(e.target.value)} required />
          <input className={box} type="password" autoComplete="new-password" placeholder="password (10+ characters)" value={password} onChange={(e) => setPassword(e.target.value)} required />
          <select className={box} value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="planner">planner</option>
            <option value="reviewer">reviewer</option>
            <option value="admin">admin</option>
          </select>
          <button className={box} type="submit">Add user</button>
        </form>
        {msg && <p className="text-ink-muted">{msg}</p>}
      </div>
    </section>
  );
}
