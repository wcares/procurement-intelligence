import { RoleOnly } from "@/components/auth";
import { EvaluationView } from "@/components/evaluation/evaluation-view";

export default function EvaluationPage() {
  return (
    <div className="w-full">
      <h1 className="text-3xl font-semibold text-brand-strong">Quality</h1>
      <p className="mt-2 mb-8 max-w-prose text-ink-muted">
        How well the system works, measured on a fixed set of 80 planner questions with judged answers and on the award times
        of past packages. The numbers update after each refresh, retrain or change.
      </p>
      <RoleOnly role="reviewer">
        <EvaluationView />
      </RoleOnly>
    </div>
  );
}
