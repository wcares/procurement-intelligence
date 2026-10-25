import { AdminOnly } from "@/components/auth";
import { RulesView } from "@/components/pipeline/rules-view";

export default function RulesPage() {
  return (
    <AdminOnly>
      <RulesView />
    </AdminOnly>
  );
}
