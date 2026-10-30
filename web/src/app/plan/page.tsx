import { Suspense } from "react";
import { PlanView } from "@/components/plan/plan-view";

export default function PlanPage() {
  return (
    <Suspense fallback={<p className="text-sm text-ink-muted">Loading…</p>}>
      <PlanView />
    </Suspense>
  );
}
