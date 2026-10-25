import { PipelineTabs } from "@/components/pipeline/tabs";

/** The admin pipeline area (each page checks the role, so the page segment always renders): where data comes from, what changed, and what the rules do with it. */
export default function PipelineLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="text-2xl font-semibold tracking-tight">Data pipeline</h1>
      <p className="mt-2 mb-4 text-muted">
        Each source is read on its interval; only what changed is processed, by the rules. The weekly refresh still
        rebuilds everything as a reconciliation.
      </p>
      <PipelineTabs />
      <div className="mt-6">{children}</div>
    </div>
  );
}
