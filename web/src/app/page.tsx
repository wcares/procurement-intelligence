import { DashboardView } from "./dashboard-view";

export default function Home() {
  return (
    <>
      <div className="mb-6 max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">What went wrong in past procurement</h1>
        <p className="mt-2 text-ink-muted">
          Where and when World Bank–financed procurement was slow, re-tendered or rated poorly, worst first, from the
          projects with a completion report. Every number opens the records behind it.
        </p>
      </div>
      <DashboardView />
    </>
  );
}
