import { redirect } from "next/navigation";

// Ask the evidence is a tab of the planning workspace; old links and bookmarks land there.
export default function AskPage() {
  redirect("/plan?tab=ask");
}
