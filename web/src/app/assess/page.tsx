import { redirect } from "next/navigation";

// Assess a package is a tab of Plan a project; old links and bookmarks land there.
export default function AssessPage() {
  redirect("/plan?tab=assess");
}
