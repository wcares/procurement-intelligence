import { Suspense } from "react";
import { InsightsView } from "@/components/insights/insights-view";

export default function InsightsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-ink-muted">Loading…</p>}>
      <InsightsView />
    </Suspense>
  );
}
