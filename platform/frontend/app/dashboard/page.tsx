import { redirect } from "next/navigation";

/** The dashboard became `/work` (SPEC-019). The rename carries the change:
 * the old page led with how many patients fall into each risk bucket, which
 * is a fact about the panel rather than a thing to do.
 *
 * Kept as a redirect because `/dashboard` is where every existing bookmark,
 * every `homeFor("clinician")` call in an older session's localStorage, and
 * the login redirect all point. */
export default function DashboardRedirect() {
  redirect("/work");
}
