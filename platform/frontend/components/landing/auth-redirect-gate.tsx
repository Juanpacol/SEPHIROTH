"use client";

/** Soft-navigation fallback for `AUTH_GATE_SCRIPT` — the inline `<head>`
 * script only runs on a full page load. A client-side nav back to "/"
 * (e.g. clicking the logo from `/dashboard`) needs this instead. */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredUser, homeFor } from "@/lib/auth";

export default function AuthRedirectGate() {
  const router = useRouter();

  useEffect(() => {
    const user = getStoredUser();
    if (user) router.replace(homeFor(user.role));
  }, [router]);

  return null;
}
