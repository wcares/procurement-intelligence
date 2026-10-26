import { AdminOnly } from "@/components/auth";
import { StatusRulesView } from "@/components/pipeline/status-rules-view";

export default function StatusRulesPage() {
  return (
    <AdminOnly>
      <StatusRulesView />
    </AdminOnly>
  );
}
