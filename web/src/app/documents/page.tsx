import { UploadView } from "@/components/pipeline/upload-view";

export default function DocumentsPage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-2xl font-semibold tracking-tight">Your documents</h1>
      <p className="mt-2 mb-6 text-ink-muted">
        Add reports and procurement documents to have them read, classified and linked to the projects they name. A
        completion report, supervision report (ISR) or restructuring paper about a tracked project joins the evidence
        everyone searches once an admin confirms it.
      </p>
      <UploadView />
    </div>
  );
}
