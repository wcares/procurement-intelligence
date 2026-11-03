"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Account } from "@/lib/api/types";
import { useAuth } from "@/components/auth";

const box = "rounded-md border border-line bg-surface px-2 py-1 text-xs";

/** Accounts and roles (admins), and access requests from the sign-up page, approved with a role or declined. Passwords
 * are set here or with `python -m procintel.auth`, never shown. */
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
  const requests = list.filter((u) => u.requestedAt && !u.active);
  return (
    <section>
      <h2 className="mb-4 text-xl font-semibold">Accounts</h2>
      <div className="space-y-3 rounded-lg border border-line bg-surface p-5 text-xs">
        <p className="text-ink-muted">Planners use Assess and Ask; admins also see Settings. A change signs the person out.</p>
        {requests.length > 0 && <Requests requests={requests} apply={apply} />}
        <table className="w-full text-left">
          <thead className="text-ink-muted"><tr><th>User</th><th>Role</th><th>Status</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {list.filter((u) => !requests.includes(u)).map((u) => (
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

/** Access requests waiting for approval: approving enables the account with the role chosen here (planner unless
 * changed), declining removes the request. */
function Requests({ requests, apply }: { requests: Account[]; apply: (r: { users: Account[] } | { error: string }, ok: string) => Promise<void> }) {
  const [roles, setRoles] = useState<Record<string, string>>({});
  async function approve(name: string) {
    const role = roles[name] ?? "planner";
    if (role !== "planner") {
      const r = await api.updateUser(name, { role });
      if ("error" in r) return apply(r, "");
    }
    await apply(await api.updateUser(name, { active: true }), `${name} approved as ${role}.`);
  }
  async function decline(name: string) {
    await apply(await api.declineRequest(name).catch((e: Error) => ({ error: e.message })), `The request from ${name} was declined.`);
  }
  return (
    <div className="space-y-2 rounded-md border border-line bg-risk-medium-soft p-3">
      <p className="font-medium">Access requests ({requests.length})</p>
      <table className="w-full text-left">
        <tbody>
          {requests.map((u) => (
            <tr key={u.username} className="border-t border-line first:border-t-0">
              <td className="py-1 font-medium">{u.username}</td>
              <td className="text-ink-muted">asked {u.requestedAt ? new Date(u.requestedAt).toLocaleString() : ""}</td>
              <td>
                <select className={box} aria-label={`Role for ${u.username}`} value={roles[u.username] ?? "planner"}
                  onChange={(e) => setRoles({ ...roles, [u.username]: e.target.value })}>
                  <option value="planner">planner</option>
                  <option value="reviewer">reviewer</option>
                  <option value="admin">admin</option>
                </select>
              </td>
              <td className="space-x-3 text-right">
                <button className="font-medium text-brand underline" onClick={() => void approve(u.username)}>approve</button>
                <button className="underline" onClick={() => void decline(u.username)}>decline</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
