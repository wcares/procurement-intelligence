import { AdminOnly } from "@/components/auth";
import { ConfigView } from "./config-view";

export default function ConfigPage() {
  return (
    <>
      <div className="mb-8 border-b border-line pb-6">
        <h1 className="text-3xl font-semibold text-brand-strong">Settings</h1>
        <p className="mt-2 text-ink-muted">Accounts, models and search. A saved setting applies to the next request and stays after a restart; API keys live in the environment and are never shown.</p>
      </div>
      <AdminOnly>
        <ConfigView />
      </AdminOnly>
    </>
  );
}
