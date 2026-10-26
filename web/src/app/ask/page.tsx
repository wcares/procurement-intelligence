import { AskView } from "./ask-view";

export default function AskPage() {
  return (
    <>
      <div className="mx-auto mb-8 max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Ask the evidence</h1>
        <p className="mt-2 text-ink-muted">
          Questions are answered from World Bank completion reports, supervision reports (ISRs) and restructuring papers.
          Each sentence links to the passage it comes from.
        </p>
      </div>
      <AskView />
    </>
  );
}
