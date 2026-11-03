import { redirect } from "next/navigation";

/** The old single sign-in page: the landing page now offers the planner and the administrator sign-in. */
export default function LoginPage() {
  redirect("/welcome");
}
