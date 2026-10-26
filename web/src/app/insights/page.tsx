import { InsightsView } from "@/components/insights/insights-view";

export default function InsightsPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
      <p className="mt-2 mb-6 text-muted">Alerts on what you follow, from the changes the pipeline detects in the World Bank data.</p>
      <InsightsView />
    </div>
  );
}
