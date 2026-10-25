"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/auth";

const TABS = [
  { href: "/pipeline", label: "Connectors" },
  { href: "/pipeline/events", label: "Event log" },
  { href: "/pipeline/rules", label: "Rules" },
];

export function PipelineTabs() {
  const path = usePathname();
  const { user } = useAuth();
  if (user?.role !== "admin") return null;
  return (
    <nav className="flex gap-1 border-b border-line text-sm">
      {TABS.map((t) => (
        <Link key={t.href} href={t.href}
          className={`-mb-px border-b-2 px-3 py-2 ${path === t.href ? "border-accent font-medium" : "border-transparent text-muted hover:text-foreground"}`}>
          {t.label}
        </Link>
      ))}
    </nav>
  );
}
