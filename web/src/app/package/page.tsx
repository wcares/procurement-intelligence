import { Suspense } from "react";
import { PackageView } from "@/components/monitoring/package-view";

export default function PackagePage() {
  return (
    <div className="w-full">
      <Suspense fallback={<p className="text-sm text-ink-muted">Loading…</p>}>
        <PackageView />
      </Suspense>
    </div>
  );
}
