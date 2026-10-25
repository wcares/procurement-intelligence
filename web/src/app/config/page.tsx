import { AdminOnly } from "@/components/auth";
import { ConfigView } from "./config-view";

export default function ConfigPage() {
  return (
    <>
      <div className="mx-auto mb-8 max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-muted">
          Backend settings, applied to the next request. Save to keep them after a restart. API keys are set in the
          environment and never shown here.
        </p>
      </div>
      <AdminOnly>
        <ConfigView />
      </AdminOnly>
    </>
  );
}
