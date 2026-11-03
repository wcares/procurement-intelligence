"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { Account } from "@/lib/api/types";
import { useAuth } from "@/components/auth";

const box = "rounded-md border border-line bg-surface px-2 py-1 text-xs";

/** Accounts and roles (admins), and access requests from the sign-up page, approved with a role or declined. An account
 * can be disabled (kept, cannot sign in) or removed after a confirmation on the row (with its saved conversations,
 * watch-list and alerts). Passwords are set here or with `python -m procintel.auth`, never shown. */
export function Users() {
  const { user } = useAuth();
  const [list, setList] = useState<Account[] | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("planner");
  const [msg, setMsg] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);   // the account whose removal is being confirmed

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
        {msg && <p role="status" className="text-sm font-medium">{msg}</p>}
        {requests.length > 0 && <Requests requests={requests} apply={apply} />}
        <table className="w-full text-left">
          <thead className="text-ink-muted"><tr><th>User</th><th>Role</th><th>Clearance</th><th>Status</th><th>Last sign-in</th><th /></tr></thead>
          <tbody>
            {list.filter((u) => !requests.includes(u)).map((u) => (
              <tr key={u.username} className="border-t border-line">
                <td className="py-1 font-medium">{u.username}</td>
                <td>
                  <select className={box} value={u.role} disabled={u.username === user.username}
                    onChange={async (e) => apply(await api.updateUser(u.username, { role: e.target.value }), `${u.username} is now ${e.target.value}.`)}>
                    <option value="planner">planner</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td>
                  {/* planned: not stored or enforced yet (see the Permission levels section below) */}
                  <select className={`${box} opacity-50`} disabled value="1" aria-label={`Clearance for ${u.username} (planned)`} title="Planned: not in use yet">
                    <option value="1">Level 1</option>
                  </select>
                </td>
                <td>{u.active ? "active" : "disabled"}</td>
                <td>{u.lastLogin ? new Date(u.lastLogin).toLocaleString() : "never"}</td>
                <td className="whitespace-nowrap text-right">
                  {u.username !== user.username && (removing === u.username ? (
                    <span className="inline-flex items-center gap-2">
                      <span className="text-risk-high">Remove {u.username} and their saved conversations?</span>
                      <button type="button" className="rounded-md bg-risk-high px-3 py-1 font-medium text-white"
                        onClick={async () => {
                          setRemoving(null);
                          await apply(await api.removeUser(u.username).catch((e: Error) => ({ error: e.message })), `${u.username} removed.`);
                        }}>
                        Remove
                      </button>
                      <button type="button" className="underline" onClick={() => setRemoving(null)}>cancel</button>
                    </span>
                  ) : (
                    <span className="space-x-3">
                      <button type="button" className="underline" onClick={async () => apply(await api.updateUser(u.username, { active: !u.active }).catch((e: Error) => ({ error: e.message })), `${u.username} ${u.active ? "disabled" : "enabled"}.`)}>
                        {u.active ? "disable" : "enable"}
                      </button>
                      <button type="button" className="text-risk-high underline" onClick={() => setRemoving(u.username)}>remove</button>
                    </span>
                  ))}
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
            <option value="admin">admin</option>
          </select>
          <button className={box} type="submit">Add user</button>
        </form>
      </div>
      <PermissionLevels />
    </section>
  );
}

/** Planned, shown greyed out: clearance levels per user and per document, applied every time someone searches. Nothing
 * here is stored or enforced yet; the backend knows nothing of it. */
function PermissionLevels() {
  const levels = [
    ["1", "Public", "World Bank open data: projects, notices, awards and published reports. Everyone."],
    ["2", "Internal", "Uploaded documents and records from connected systems marked internal."],
    ["3", "Restricted", "Bid evaluations, supplier correspondence and other confidential files."],
  ];
  return (
    <div className="mt-6 space-y-3 rounded-lg border border-dashed border-line p-5 text-xs opacity-60" aria-disabled="true">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold">Permission levels</h3>
        <span className="rounded border border-line px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ink-muted">Planned</span>
      </div>
      <p className="text-ink-muted">
        Each document gets a level at intake and each user a clearance; search, the chat, assessments, exports and shared links
        show only what the user may see, checked on every request. Not in use yet: all documents are public today.
      </p>
      <table className="w-full text-left">
        <thead className="text-ink-muted"><tr><th>Level</th><th>Name</th><th>Who sees it and what it holds</th></tr></thead>
        <tbody>
          {levels.map(([n, name, what]) => (
            <tr key={n} className="border-t border-line"><td className="py-1 font-mono">{n}</td><td className="font-medium">{name}</td><td>{what}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled className={box}>Set a document&apos;s level at intake</button>
        <button type="button" disabled className={box}>Default clearance for new accounts: 1</button>
      </div>
    </div>
  );
}

/** Access requests waiting for approval: approving enables the account with the role chosen here (planner unless
 * changed), declining removes the request. A failed call shows its error in the panel instead of doing nothing. */
function Requests({ requests, apply }: { requests: Account[]; apply: (r: { users: Account[] } | { error: string }, ok: string) => Promise<void> }) {
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const failed = (e: Error) => ({ error: e.message });
  async function run(name: string, work: () => Promise<void>) {
    setBusy(name);
    try {
      await work();
    } finally {
      setBusy(null);
    }
  }
  const approve = (name: string) => run(name, async () => {
    const role = roles[name] ?? "planner";
    if (role !== "planner") {
      const r = await api.updateUser(name, { role }).catch(failed);
      if ("error" in r) return apply(r, "");
    }
    await apply(await api.updateUser(name, { active: true }).catch(failed), `${name} approved as ${role}.`);
  });
  const decline = (name: string) => run(name, async () =>
    apply(await api.removeUser(name).catch(failed), `The request from ${name} was declined.`));
  return (
    <div className="space-y-3 rounded-md border border-brand-2 bg-brand-soft p-4">
      <p className="text-sm font-semibold">Access requests ({requests.length})</p>
      <ul className="space-y-2">
        {requests.map((u) => (
          <li key={u.username} className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md bg-surface px-3 py-2">
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">{u.username}</span>
              <span className="text-ink-muted">asked {u.requestedAt ? new Date(u.requestedAt).toLocaleString() : ""}</span>
            </span>
            <label className="flex items-center gap-2">
              Role
              <select className={box} value={roles[u.username] ?? "planner"} disabled={busy === u.username}
                onChange={(e) => setRoles({ ...roles, [u.username]: e.target.value })}>
                <option value="planner">planner</option>
                                <option value="admin">admin</option>
              </select>
            </label>
            <button type="button" disabled={busy !== null} onClick={() => void approve(u.username)}
              className="rounded-md bg-brand px-4 py-1.5 text-xs font-medium text-on-brand disabled:opacity-50">
              {busy === u.username ? "Working…" : "Approve"}
            </button>
            <button type="button" disabled={busy !== null} onClick={() => void decline(u.username)}
              className="rounded-md border border-line bg-surface px-4 py-1.5 text-xs font-medium hover:bg-subtle disabled:opacity-50">
              Decline
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
