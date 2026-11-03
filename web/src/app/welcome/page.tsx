import Link from "next/link";
import { Activity, ArrowRight, BookOpen, ClipboardList, Clock, ShieldCheck, TriangleAlert } from "lucide-react";

export const metadata = { title: "Procurement Intelligence" };

// What a planner gets, one line per question (the planner deck, docs/Procurement Intelligence - Planners.pptx).
const ANSWERS = [
  { icon: Clock, q: "How long will it take?", a: "A typical award time from comparable past tenders, a model estimate, and the chance of over 6 months." },
  { icon: TriangleAlert, q: "What could go wrong?", a: "Risk flags with their level, whether each is a statistic or a model, and the records behind it." },
  { icon: BookOpen, q: "What did others learn?", a: "Lessons from completion reports, every sentence cited and checked against its source." },
  { icon: Activity, q: "Is it on track?", a: "A status and a forecast from today for each package, early warnings and alerts." },
];

const DATA = [["153", "projects in 80 countries"], ["12,152", "procurement notices"], ["17,678", "contract awards"], ["28,775", "citable passages"]];

/** The landing page for visitors without a session: what the tool does, and the two ways in (planners, who may also
 * request an account, and administrators). */
export default function Welcome() {
  return (
    <div className="mx-auto max-w-6xl space-y-14 py-4">
      <section className="grid gap-10 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] lg:items-start">
        <div className="min-w-0 space-y-5">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-brand-2">Procurement planning, with evidence</p>
          <h1 className="text-4xl font-semibold tracking-tight text-brand-strong text-balance">
            Plan procurement with what past projects already know
          </h1>
          <p className="max-w-xl text-lg text-ink-muted">
            Contract awards, supervision reports and completion reports, linked by project and searched for you, so a
            package is planned on how similar tenders actually went, not on a guess.
          </p>
          <dl className="grid max-w-xl grid-cols-2 gap-x-6 gap-y-4 pt-2 sm:grid-cols-4">
            {DATA.map(([n, l]) => (
              <div key={l}>
                <dt className="sr-only">{l}</dt>
                <dd className="font-mono text-2xl font-semibold text-brand">{n}</dd>
                <dd className="text-xs text-ink-muted">{l}</dd>
              </div>
            ))}
          </dl>
          <p className="text-xs text-ink-muted">World Bank open data, as of 1 November 2026.</p>
        </div>

        <div className="min-w-0 space-y-4">
          <div className="rounded-xl border border-line bg-surface p-6 shadow-[0_1px_3px_rgba(0,0,0,0.06)]">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-full bg-brand text-on-brand"><ClipboardList size={18} aria-hidden /></span>
              <div>
                <h2 className="font-semibold">Planners</h2>
                <p className="text-sm text-ink-muted">Assess packages, plan projects, ask the evidence.</p>
              </div>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <Link href="/login/planner" className="inline-flex items-center gap-1.5 rounded-md bg-brand px-4 py-2 text-sm font-medium text-on-brand">
                Planner sign-in <ArrowRight size={14} aria-hidden />
              </Link>
              <Link href="/signup" className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:bg-subtle">Request access</Link>
            </div>
            <p className="mt-3 text-xs text-ink-muted">Reviewers sign in here too. A new account works once an administrator approves it.</p>
          </div>

          <div className="rounded-xl border border-line bg-subtle p-6">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-full bg-brand-strong text-on-brand"><ShieldCheck size={18} aria-hidden /></span>
              <div>
                <h2 className="font-semibold">Administrators</h2>
                <p className="text-sm text-ink-muted">Run the data pipeline, models, accounts and settings.</p>
              </div>
            </div>
            <div className="mt-5">
              <Link href="/login/admin" className="inline-flex items-center gap-1.5 rounded-md border border-brand px-4 py-2 text-sm font-medium text-brand hover:bg-brand-soft">
                Administrator sign-in <ArrowRight size={14} aria-hidden />
              </Link>
            </div>
            <p className="mt-3 text-xs text-ink-muted">Administrator accounts are created by an administrator.</p>
          </div>
        </div>
      </section>

      <section className="space-y-5">
        <h2 className="text-xl font-semibold">The questions a planner asks, answered with sources</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {ANSWERS.map(({ icon: Icon, q, a }) => (
            <div key={q} className="min-w-0 space-y-2 rounded-lg border border-line bg-surface p-5">
              <Icon size={20} className="text-brand-2" aria-hidden />
              <h3 className="font-semibold">{q}</h3>
              <p className="text-sm text-ink-muted">{a}</p>
            </div>
          ))}
        </div>
        <p className="text-sm text-ink-muted">
          Every number says how many past packages it rests on; with no supporting evidence, the tool says so instead of guessing.
        </p>
      </section>
    </div>
  );
}
