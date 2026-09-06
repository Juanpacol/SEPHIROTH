/** Route classification shared by `AppShell` and the auth guard. */

/** Exact-match only — a prefix test on "/" would strip chrome from every
 * page, so these are compared with `===`, never `startsWith`. */
export const CHROMELESS_ROUTES = ["/login", "/", "/portal/claim"] as const;

export function isChromelessRoute(pathname: string): boolean {
  return (CHROMELESS_ROUTES as readonly string[]).includes(pathname);
}

/** Every clinician-reachable prefix, including the ones that now only serve a
 * redirect. The stubs still have to pass `AuthGuard` — a route missing from
 * this list is treated as not-a-clinician-route and bounces a signed-in
 * clinician away before the redirect ever runs, which turns an old bookmark
 * into a logout rather than a forward. */
export const CLINICIAN_PREFIXES = [
  "/work",
  "/tasks",
  "/patients",
  "/agenda",
  "/alerts",
  "/approvals",
  "/results",
  "/followups",
  "/settings",
  "/admin",
  // Reachable, but no longer in the primary navigation: evidence opens from an
  // alert or a medication, imaging from a patient.
  "/evidence",
  "/imaging",
  // Redirect stubs kept for existing links and bookmarks.
  "/dashboard",
  "/schedule",
  "/agents",
  "/copilot",
  "/profile",
  "/preferences",
] as const;

export const PATIENT_PREFIXES = ["/portal"] as const;

export function isClinicianRoute(pathname: string): boolean {
  return CLINICIAN_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

export function isPatientRoute(pathname: string): boolean {
  return PATIENT_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"));
}
