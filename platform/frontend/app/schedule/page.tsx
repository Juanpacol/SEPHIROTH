import { redirect } from "next/navigation";

/** The weekly agenda moved to `/agenda` (SPEC-019) — "schedule" named the
 * thing a clinician configures, "agenda" names the thing they read.
 *
 * A redirect stub rather than a `middleware.ts` rewrite: the JWT lives in
 * `localStorage` and is invisible to middleware, so introducing one here would
 * mean either an unauthenticated redirect or moving the token to a cookie,
 * which is an explicit non-goal (CLAUDE.md decision #22). This is the same
 * pattern `/copilot` already uses, and it costs one server component. */
export default function ScheduleRedirect() {
  redirect("/agenda");
}
