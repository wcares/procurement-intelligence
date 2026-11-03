import Link from "next/link";
import { SignUpView } from "./signup-view";

export const metadata = { title: "Request access · Procurement Intelligence" };

export default function SignUp() {
  return (
    <div className="mx-auto mt-10 max-w-sm space-y-6">
      <div>
        <Link href="/welcome" className="text-xs text-ink-muted underline underline-offset-2">← Procurement Intelligence</Link>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">Request access</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Ask for a planner account. It works once an administrator approves it; administrator accounts are created by an
          administrator.
        </p>
      </div>
      <SignUpView />
      <p className="text-center text-sm text-ink-muted">
        Already approved? <Link href="/login/planner" className="underline underline-offset-2">Planner sign-in</Link>
      </p>
    </div>
  );
}
