import { AskView } from "./ask-view";

export default function AskPage() {
  return (
    <>
      <div className="mx-auto mb-8 max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Ask the evidence</h1>
        <p className="mt-2 text-muted">
          Questions are answered from Implementation Completion Reports. Each sentence links to the passage it comes from.
        </p>
      </div>
      <AskView />
    </>
  );
}
