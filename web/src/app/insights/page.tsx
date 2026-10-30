import { Suspense } from "react";
import { InsightsView } from "@/components/insights/insights-view";

export default function InsightsPage() {
  return (
    <div className="w-full">
      <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
      <p className="mt-2 mb-6 text-ink-muted">Alerts on what you follow, from the changes the pipeline detects in the World Bank data.</p>
      <Suspense fallback={<p className="text-sm text-ink-muted">Loading…</p>}>
        <InsightsView />
      </Suspense>
    </div>
  );
}
