import { AdminOnly } from "@/components/auth";
import { ConnectorsView } from "@/components/pipeline/connectors-view";

export default function ConnectorsPage() {
  return (
    <AdminOnly>
      <ConnectorsView />
    </AdminOnly>
  );
}
