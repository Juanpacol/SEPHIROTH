"use client";

/** Client-side role/auth gate — the frontend's job here is UX (don't show
 * a patient a Copilot link), not security: every underlying API call is
 * enforced server-side regardless. No `middleware.ts` — the token lives
 * in `localStorage`, invisible to Next middleware, so there is nothing a
 * server-side gate could decide on here.
 *
 * Rendering `null` while `checked` is false also fixes the pre-existing
 * "logged-out users briefly see chrome" flash: this component sits above
 * `Sidebar`/`Topbar` in `AppShell`, so nothing paints until the role is
 * known. */

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getStoredUser, homeFor, redirectToLogin } from "@/lib/auth";
import { isClinicianRoute, isPatientRoute } from "@/lib/routes";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const user = getStoredUser();
    if (!user) {
      redirectToLogin();
      return;
    }
    const wrongRole =
      (user.role === "patient" && isClinicianRoute(pathname)) ||
      (user.role === "clinician" && isPatientRoute(pathname));
    if (wrongRole) {
      router.replace(homeFor(user.role));
      return;
    }
    setChecked(true);
    // Re-run on every route change — a same-tab role switch (a second tab
    // logging in as someone else) should re-gate the next navigation.
  }, [pathname, router]);

  if (!checked) return null;
  return <>{children}</>;
}
