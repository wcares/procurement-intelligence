export const metadata = { title: "How your data is handled · Procurement Intelligence" };

/** The data-handling note for pilot participants (docs/pilot-plan.md, "Needed before the pilot"). Readable without
 * signing in. Keep it true: change it with the code it describes (procintel.learning.feedback, procintel.auth). */
export default function DataHandling() {
  return (
    <article className="mx-auto max-w-2xl space-y-5 text-sm leading-relaxed">
      <h1 className="text-2xl font-semibold tracking-tight">How your data is handled</h1>
      <section>
        <h2 className="font-semibold">What is recorded</h2>
        <ul className="ml-5 list-disc space-y-1">
          <li>What you enter in Assess (country, procurement type and method, sector, value, description, tender reference) and the questions you ask, with the full response shown to you.</li>
          <li>How long each response took, and when it was given.</li>
          <li>Your ratings, flagged citations and comments.</li>
          <li>
            A pseudonymous id instead of your name: a code derived from your account that the logs cannot be traced back
            to without a secret kept separately on the server.
          </li>
        </ul>
      </section>
      <section>
        <h2 className="font-semibold">Why</h2>
        <p>
          To measure whether the tool helps (how often it is used, whether answers are rated useful, whether predicted
          award times match the actual ones), and to improve it: refused or unhelpful questions are reviewed and added to
          the evaluation set.
        </p>
      </section>
      <section>
        <h2 className="font-semibold">Where it goes</h2>
        <p>
          In this installation the language and search models run on the server itself, so your questions and entries
          are not sent to any outside service. The tool reads only public World Bank data from the World Bank&apos;s own
          websites. If an administrator ever connects a hosted model, this page will say which one before it is used.
        </p>
        <p className="mt-2">
          Administrators can also upload documents. Each is stored on the server and read there (its text, its kind,
          the projects it names); a completion report about a tracked project becomes part of the evidence everyone
          searches. Uploaded files are not sent anywhere.
        </p>
      </section>
      <section>
        <h2 className="font-semibold">How long it is kept</h2>
        <p>
          30 days, then deleted by a daily job. While a pilot runs, your entries, the responses and your ratings are
          kept until the pilot ends (its measures cover its whole length), and deleted 30 days after.
        </p>
        <p className="mt-2">
          Uploaded documents are not deleted after 30 days: they are kept, like the World Bank reports, until an
          administrator removes them from the server (there is no remove button yet).
        </p>
      </section>
      <section>
        <h2 className="font-semibold">Your account</h2>
        <p>
          Passwords are stored only as salted hashes. Sessions end after 12 hours or when you sign out, and repeated
          failed sign-ins are paused for 15 minutes. Administrators can see the logs and manage accounts.
        </p>
      </section>
    </article>
  );
}
