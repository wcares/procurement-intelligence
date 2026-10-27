import { PlanView } from "@/components/plan/plan-view";

export default function PlanPage() {
  return (
    <>
      <div className="mb-8 max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight">Plan a project</h1>
        <p className="mt-2 text-ink-muted">
          List the packages a new project will procure. Each is forecast from comparable past packages, and the forecasts
          are laid out on one timeline with the likely bottleneck.
        </p>
      </div>
      <PlanView />
    </>
  );
}
