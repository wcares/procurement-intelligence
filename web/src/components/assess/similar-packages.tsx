import type { SimilarPackage } from "@/lib/api/types";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });

export function SimilarPackages({ items }: { items: SimilarPackage[] }) {
  return (
    <div>
      <h3 className="mb-1 font-semibold">Similar past contracts</h3>
      <p className="mb-3 text-xs text-muted">Awarded packages whose description is closest to yours, and how long they took from tender to award.</p>
      <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
        {items.map((p) => (
          <li key={p.packageId} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 py-3 text-sm">
            <span className="min-w-0 flex-1 basis-64">{p.description}</span>
            <span className="text-xs text-muted">
              {p.projectId} · {p.countryCode} · {p.method}
            </span>
            <span className="tabular-nums">{p.tenderToAwardDays != null ? `${p.tenderToAwardDays} days` : "time not known"}</span>
            {p.valueUsd != null && <span className="tabular-nums text-muted">{usd.format(p.valueUsd)}</span>}
            {p.rebid && <span className="rounded bg-risk-medium-soft px-1.5 py-0.5 text-xs text-risk-medium">re-tendered</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
