import { redirect } from "next/navigation";

/** Automation preferences are a section of `/settings` now (SPEC-019). */
export default function PreferencesRedirect() {
  redirect("/settings?section=automation");
}
