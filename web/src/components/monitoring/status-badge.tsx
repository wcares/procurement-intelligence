import type { PackageStatus } from "@/lib/api/types";

const STYLE: Record<PackageStatus, string> = {
  active: "bg-accent-soft text-accent", finished: "bg-risk-low-soft text-risk-low",
  replaced: "bg-subtle text-muted", stale: "bg-risk-medium-soft text-risk-medium",
};

export function StatusBadge({ status, phase }: { status: PackageStatus; phase?: string | null }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs ${STYLE[status]}`}>
      {status}{phase ? ` · ${phase === "bidding" ? "in bidding" : "contract running"}` : ""}
    </span>
  );
}
