/** The renames of SPEC-019, held in place.
 *
 * Renaming a route is cheap; leaving a dead link behind is not. Every old URL
 * is a bookmark, a browser history entry, or a `homeFor()` result already
 * written into somebody's `localStorage` from a previous session — so each one
 * has to keep working, and each one has to pass `AuthGuard` on the way through,
 * or the redirect never runs and the clinician is bounced to `/login` instead.
 *
 * These are file-level assertions rather than rendered ones because a Next
 * server component that calls `redirect()` cannot be rendered by jsdom: the
 * redirect throws a framework control-flow signal, not a return value.
 *
 * Verifies AC-019-01, AC-019-02 (docs/specs/SPEC-019-work-center.md).
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { CLINICIAN_PREFIXES, isClinicianRoute } from "@/lib/routes";
import { CLINICIAN_NAV, PATIENT_NAV, flatNav } from "@/lib/nav";

const ROOT = join(__dirname, "..", "..");

/** old route -> where it now goes. */
const REDIRECTS: Record<string, string> = {
  "app/dashboard/page.tsx": "/work",
  "app/schedule/page.tsx": "/agenda",
  "app/agents/page.tsx": "/admin/ai",
  "app/profile/page.tsx": "/settings",
  "app/preferences/page.tsx": "/settings",
  "app/copilot/page.tsx": "/work",
};

describe("SPEC-019 route restructure", () => {
  it("AC-019-01 — every renamed route still resolves, to its new home", () => {
    for (const [file, destination] of Object.entries(REDIRECTS)) {
      const path = join(ROOT, file);
      expect(existsSync(path), `${file} is missing — an old link would 404`).toBe(true);

      const source = readFileSync(path, "utf8");
      expect(source, `${file} should redirect`).toMatch(/redirect\(/);
      expect(source, `${file} should point at ${destination}`).toContain(destination);
    }
  });

  it("AC-019-02 — a redirect stub is still classified as a clinician route", () => {
    // Without this, `AuthGuard` treats the stub as foreign territory and
    // bounces a signed-in clinician away *before* the redirect runs, turning
    // an old bookmark into a logout.
    for (const file of Object.keys(REDIRECTS)) {
      const route = "/" + file.replace(/^app\//, "").replace(/\/page\.tsx$/, "");
      expect(isClinicianRoute(route), `${route} must pass AuthGuard`).toBe(true);
    }
  });

  it("every navigation destination has a page behind it", () => {
    for (const item of [...flatNav(CLINICIAN_NAV), ...flatNav(PATIENT_NAV)]) {
      const candidates = [
        join(ROOT, "app", item.href.slice(1), "page.tsx"),
        join(ROOT, "app", "(marketing)", item.href.slice(1), "page.tsx"),
      ];
      expect(
        candidates.some(existsSync),
        `${item.href} is in the nav with no page behind it`,
      ).toBe(true);
    }
  });

  it("every navigation destination is reachable past the auth guard", () => {
    for (const item of flatNav(CLINICIAN_NAV)) {
      expect(isClinicianRoute(item.href), `${item.href} must pass AuthGuard`).toBe(true);
    }
  });

  it("the nav is flat — grouping described the system, not the work", () => {
    expect(CLINICIAN_NAV).toHaveLength(1);
    expect(CLINICIAN_NAV[0].groupId).toBeNull();
  });

  it("keeps the demoted destinations reachable, just not in the nav", () => {
    // Nothing was deleted: evidence opens from an alert or a medication,
    // imaging from a patient, agent activity from /admin.
    const navHrefs = new Set(flatNav(CLINICIAN_NAV).map((i) => i.href));
    for (const demoted of ["/evidence", "/imaging"]) {
      expect(navHrefs.has(demoted)).toBe(false);
      expect(CLINICIAN_PREFIXES).toContain(demoted);
      expect(existsSync(join(ROOT, "app", demoted.slice(1), "page.tsx"))).toBe(true);
    }
  });
});
