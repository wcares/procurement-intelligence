import { AssessView } from "./assess-view";

export default function AssessPage() {
  return (
    <>
      <div className="mb-8 max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight">Assess a procurement package</h1>
        <p className="mt-2 text-ink-muted">
          See how comparable World Bank–financed packages actually went, and what past evaluations say went wrong, with every
          lesson quoted from its source.
        </p>
      </div>
      <AssessView />
    </>
  );
}
