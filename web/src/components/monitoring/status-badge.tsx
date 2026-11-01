import type { PackageStatus } from "@/lib/api/types";

const STYLE: Record<PackageStatus, string> = {
  active: "bg-brand-soft text-brand", finished: "bg-risk-low-soft text-risk-low",
  replaced: "bg-subtle text-ink-muted", stale: "bg-risk-medium-soft text-risk-medium",
};

/** A package's status in plain words, and what it means (shown on hover). */
export const STATUS_WORD: Record<PackageStatus, string> = { active: "Active", finished: "Awarded", replaced: "Re-tendered", stale: "Stalled" };
export const STATUS_MEANING: Record<PackageStatus, string> = {
  active: "Still under way: in bidding, or awarded with the contract running.",
  finished: "The contract was awarded.",
  replaced: "Tendered again: a newer notice with the same reference continues it.",
  stale: "No award recorded, and open far longer than similar tenders took (or the project ended without one).",
};

export function StatusBadge({ status, phase }: { status: PackageStatus; phase?: string | null }) {
  return (
    <span title={STATUS_MEANING[status]} className={`rounded px-1.5 py-0.5 text-xs ${STYLE[status]}`}>
      {STATUS_WORD[status]}{phase ? ` · ${phase === "bidding" ? "in bidding" : "contract running"}` : ""}
    </span>
  );
}
