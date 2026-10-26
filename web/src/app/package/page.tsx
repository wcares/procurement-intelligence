import { Suspense } from "react";
import { PackageView } from "@/components/monitoring/package-view";

export default function PackagePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
        <PackageView />
      </Suspense>
    </div>
  );
}
