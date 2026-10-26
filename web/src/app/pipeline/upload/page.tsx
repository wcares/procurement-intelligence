import { AdminOnly } from "@/components/auth";
import { UploadView } from "@/components/pipeline/upload-view";

export default function UploadPage() {
  return (
    <AdminOnly>
      <UploadView />
    </AdminOnly>
  );
}
