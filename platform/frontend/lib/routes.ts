/** Route classification shared by `AppShell` and the auth guard. */

/** Exact-match only — a prefix test on "/" would strip chrome from every
 * page, so these are compared with `===`, never `startsWith`. */
export const CHROMELESS_ROUTES = ["/login", "/", "/portal/claim"] as const;

export function isChromelessRoute(pathname: string): boolean {
  return (CHROMELESS_ROUTES as readonly string[]).includes(pathname);
}

export const CLINICIAN_PREFIXES = [
  "/dashboard",
  "/copilot",
  "/patients",
  "/evidence",
  "/imaging",
  "/agents",
  "/schedule",
  "/profile",
  "/recommendations",
  "/approvals",
  "/alerts",
] as const;

export const PATIENT_PREFIXES = ["/portal"] as const;

export function isClinicianRoute(pathname: string): boolean {
  return CLINICIAN_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

export function isPatientRoute(pathname: string): boolean {
  return PATIENT_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"));
}
