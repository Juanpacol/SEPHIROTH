"use client";

/** Client-side auth state: JWT in localStorage, helpers, and a user hook. */

import { useEffect, useState } from "react";

const TOKEN_KEY = "cac_token";
const USER_KEY = "cac_user";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: "clinician" | "patient";
  patient_id: string | null;
}

/** Where a role lands after login/logout — the one place this mapping
 * lives, so the login page, the auth guard, and the post-logout redirect
 * all agree. */
export function homeFor(role: AuthUser["role"]): string {
  return role === "patient" ? "/portal" : "/dashboard";
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as AuthUser) : null;
}

export function storeAuth(token: string, user: AuthUser): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/** Patch the cached user after a successful profile edit. */
export function updateStoredUser(user: AuthUser): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Redirect to /login, remembering nothing (demo scope).
 *
 * Clears the stale token/user first — a 401 means the session is dead
 * (expired/invalid JWT), and leaving it in localStorage sent every future
 * visit to "/" straight back into the dead session via `AUTH_GATE_SCRIPT`
 * (which only checks *presence* of a token, not validity), bouncing
 * landing -> dashboard -> 401 -> login in a loop that never showed the
 * landing page or a real dashboard. */
export function redirectToLogin(): void {
  clearAuth();
  if (typeof window !== "undefined" && window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

/** Current logged-in user (from localStorage; null while logged out).
 *
 * Reads localStorage synchronously via a lazy `useState` initializer
 * instead of starting at `null` and hydrating in a `useEffect` — every
 * consumer of this hook (`Sidebar`, `Topbar`, ...) only ever mounts
 * client-side, after `AuthGuard` has already resolved the same
 * `getStoredUser()` call in its own effect (it renders `null` until
 * then), so there is no SSR/hydration-mismatch risk here. The previous
 * null-then-hydrate version meant every one of those consumers
 * independently re-derived its role-dependent UI (nav items, home link)
 * one render late — for a fraction of a second, `Sidebar`/`Topbar` would
 * render as if logged out (falling back to the clinician-shaped
 * defaults), which read as "briefly flashes the dashboard" when landing
 * on `/portal` as a patient. */
export function useUser(): AuthUser | null {
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  useEffect(() => {
    setUser(getStoredUser());
  }, []);
  return user;
}
