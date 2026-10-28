import { PlanView } from "@/components/plan/plan-view";

export default function PlanPage() {
  return (
    <>
      <div className="mb-8 max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight">Plan a project</h1>
        <p className="mt-2 text-ink-muted">
          Tell the assistant what you want to plan, or fill the form on the Manual tab. Each package is forecast from comparable
          past packages, and the forecasts are laid out on one timeline with the likely bottleneck. Ask about the plan, or about
          what went wrong in past projects, in the same chat.
        </p>
      </div>
      <PlanView />
    </>
  );
}
