"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** A panel that slides in from the right over the page; Esc, the backdrop or the close button dismiss it. */
export function ConfigureDrawer({ open, title, subtitle, onClose, children }: {
  open: boolean; title: string; subtitle?: string; onClose: () => void; children: ReactNode;
}) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  return (
    <div className={`fixed inset-0 z-40 ${open ? "" : "pointer-events-none"}`} aria-hidden={!open}>
      <div className={`absolute inset-0 bg-black/60 transition-opacity ${open ? "opacity-100" : "opacity-0"}`} onClick={onClose} />
      <aside role="dialog" aria-modal="true" aria-label={title}
        className={`absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-line bg-surface shadow-2xl transition-transform duration-200 ${open ? "translate-x-0" : "translate-x-full"}`}>
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 className="text-base font-semibold tracking-tight">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>}
          </div>
          <button ref={close} type="button" onClick={onClose} aria-label="Close" className="grid size-8 place-items-center rounded-lg text-ink-muted hover:bg-subtle hover:text-foreground">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden><path d="M2 2l10 10M12 2L2 12" /></svg>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{open && children}</div>
      </aside>
    </div>
  );
}
