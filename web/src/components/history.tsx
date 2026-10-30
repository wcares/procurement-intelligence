"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type { SavedConversation } from "@/lib/api/types";

const newId = () => (typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);
const lastKey = (kind: string) => `procintel.lastConversation.${kind}`;
const remember = (kind: string, id: string | null) => {
  try { id ? localStorage.setItem(lastKey(kind), id) : localStorage.removeItem(lastKey(kind)); } catch { /* storage blocked: history still works from the list */ }
};

/** A conversation kept on the server: it saves itself after each finished turn, reopens after a reload, and the saved ones
 * can be listed, opened (and continued) or deleted. `items` is what the page shows; `restore` puts a saved one back. */
export function useHistory<T>(kind: "plan" | "ask", items: T[], restore: (items: T[]) => void, busy: boolean) {
  const [id, setId] = useState(newId);
  const [list, setList] = useState<SavedConversation[]>([]);
  const skip = useRef(true);   // the first change after opening one is the opening itself, not a new message
  const reload = useCallback(() => api.conversations(kind).then((r) => setList(r.items)).catch(() => null), [kind]);

  const open = useCallback(async (cid: string) => {
    const c = await api.conversation(cid).catch(() => null);
    if (!c) { remember(kind, null); return; }
    skip.current = true;
    setId(cid);
    remember(kind, cid);
    restore(c.messages as T[]);
  }, [kind, restore]);

  useEffect(() => {   // after a reload: the conversation that was open
    let last: string | null = null;
    try { last = localStorage.getItem(lastKey(kind)); } catch { /* none */ }
    if (last) void open(last);
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {   // save when a turn has finished (not while an answer is being written)
    if (skip.current) { skip.current = false; return; }
    if (!items.length || busy) return;
    const t = setTimeout(() => {
      remember(kind, id);
      api.saveConversation(id, kind, items).then(reload).catch(() => null);
    }, 400);
    return () => clearTimeout(t);
  }, [items, busy, id, kind, reload]);

  const fresh = () => { skip.current = true; setId(newId()); remember(kind, null); restore([]); };
  const remove = async (cid: string) => {
    await api.deleteConversation(cid).catch(() => null);
    if (cid === id) fresh();
    void reload();
  };
  return { id, list, open, fresh, remove };
}

const ago = (iso: string) => {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  if (m < 1440) return `${Math.round(m / 60)} h ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
};

/** The History button and its list of saved conversations. */
export function HistoryMenu({ h }: { h: ReturnType<typeof useHistory> }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[12px] text-ink-muted transition hover:bg-subtle hover:text-foreground">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden><circle cx="8" cy="8" r="6" /><path d="M8 4.5V8l2.2 1.4" /></svg>
        History{h.list.length ? ` (${h.list.length})` : ""}
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-30 mb-2 max-h-80 w-80 overflow-y-auto rounded-xl border border-line bg-surface p-1.5 shadow-2xl">
          {h.list.length === 0 ? <p className="px-3 py-3 text-xs text-ink-muted">No saved conversations yet. They are saved as you chat.</p> : h.list.map((c) => (
            <div key={c.id} className={`group flex items-center gap-1 rounded-lg px-1 ${c.id === h.id ? "bg-brand-soft" : "hover:bg-subtle"}`}>
              <button type="button" className="min-w-0 flex-1 px-2 py-2 text-left" onClick={() => { void h.open(c.id); setOpen(false); }}>
                <span className="block truncate text-sm">{c.title}</span>
                <span className="block text-[11px] text-ink-muted">{ago(c.updatedAt)} · {c.messages} messages</span>
              </button>
              <button type="button" aria-label={`Delete ${c.title}`} onClick={() => void h.remove(c.id)}
                className="grid size-7 shrink-0 place-items-center rounded-md text-ink-muted opacity-0 transition hover:bg-background hover:text-risk-high focus:opacity-100 group-hover:opacity-100">
                <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden><path d="M2 2l10 10M12 2L2 12" /></svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
