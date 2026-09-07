/** Pre-paint redirect for the landing page: a logged-in user opening "/"
 * should land straight on their dashboard/portal, never seeing the
 * landing page flash by first. Runs synchronously in `<head>` (see
 * `app/layout.tsx`), same pattern as `THEME_INIT_SCRIPT` — it executes
 * before hydration and before first paint, so there is nothing to flash.
 *
 * Deliberately no `middleware.ts`: the token lives in `localStorage`,
 * invisible to Next middleware, so a server-side redirect has nothing to
 * decide on here. This script (plus the `AuthRedirectGate` client
 * fallback for soft navigation back to "/") is the whole mechanism. */
export const AUTH_GATE_SCRIPT = `
(function () {
  try {
    if (location.pathname !== "/") return;
    if (!localStorage.getItem("cac_token")) return;
    document.documentElement.setAttribute("data-auth-redirect", "");
    var user = JSON.parse(localStorage.getItem("cac_user") || "null");
    location.replace(user && user.role === "patient" ? "/portal" : "/dashboard");
  } catch (e) {}
})();
`;
