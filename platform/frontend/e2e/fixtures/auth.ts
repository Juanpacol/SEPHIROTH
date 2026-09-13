import type { Page } from "@playwright/test";

/** Puts a signed-in session in place before the page's own scripts run.
 *
 * `addInitScript`, not a post-navigation `evaluate`: `AUTH_GATE_SCRIPT` and
 * `THEME_INIT_SCRIPT` both read localStorage from `<head>`, before first paint.
 * Seeding after `goto` would mean the gate had already decided the visitor was
 * anonymous and bounced them to /login.
 *
 * The token is never verified client-side (`components/auth-guard.tsx` only
 * checks that one exists, and every real check is server-side), so a dummy
 * string is enough — and every API call is mocked anyway. */

export type Role = "clinician" | "patient";

const USERS: Record<Role, Record<string, unknown>> = {
  clinician: {
    id: "u-clinician",
    email: "clinician@example.test",
    name: "Dr. Ana Ruiz",
    role: "clinician",
    patient_id: null,
  },
  patient: {
    id: "u-patient",
    email: "patient@example.test",
    name: "Marta Díaz",
    role: "patient",
    patient_id: "p-001",
  },
};

export async function seedAuth(page: Page, role: Role): Promise<void> {
  const user = USERS[role];
  await page.addInitScript(
    ([token, serializedUser]) => {
      localStorage.setItem("cac_token", token as string);
      localStorage.setItem("cac_user", serializedUser as string);
    },
    ["e2e-token", JSON.stringify(user)] as const,
  );
}
