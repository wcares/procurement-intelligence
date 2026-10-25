import { AdminOnly } from "@/components/auth";
import { EventLogView } from "@/components/pipeline/event-log-view";

export default function EventLogPage() {
  return (
    <AdminOnly>
      <EventLogView />
    </AdminOnly>
  );
}
