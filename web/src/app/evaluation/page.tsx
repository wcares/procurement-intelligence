import { RoleOnly } from "@/components/auth";
import { EvaluationView } from "@/components/evaluation/evaluation-view";

export default function EvaluationPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold tracking-tight">Evaluation</h1>
      <p className="mt-2 mb-6 text-ink-muted">
        How good search, answers and predictions are, how that changed after each refresh, retrain or promotion, and
        alternatives measured against what is live.
      </p>
      <RoleOnly role="reviewer">
        <EvaluationView />
      </RoleOnly>
    </div>
  );
}
