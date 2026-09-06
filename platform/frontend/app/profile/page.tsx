import { redirect } from "next/navigation";

/** Profile is a section of `/settings` now (SPEC-019) — from the outside,
 * "my details" and "how the automation behaves" are one thing. */
export default function ProfileRedirect() {
  redirect("/settings?section=profile");
}
