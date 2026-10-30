import { redirect } from "next/navigation";

// Questions about past projects are asked in the planning workspace chat; old links and bookmarks land there.
export default function AskPage() {
  redirect("/plan");
}
