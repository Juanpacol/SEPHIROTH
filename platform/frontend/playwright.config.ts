import { defineConfig, devices } from "@playwright/test";

/** Responsive regression gate.
 *
 * The suite is deliberately thin on behavior and heavy on layout: its job is to
 * fail when a page overflows its viewport or grows an untappable control, not
 * to re-test what Vitest already covers.
 *
 * WebKit carries two of the three projects on purpose — safe areas, `vh` vs
 * `dvh`, and `position: fixed` under the keyboard are Safari-only failures, and
 * a Chromium-only matrix would report green on every one of them.
 */

const PORT = 3210;
const baseURL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: { baseURL, trace: "on-first-retry" },
  projects: [
    { name: "iphone-14", use: { ...devices["iPhone 14"] } },
    { name: "ipad", use: { ...devices["iPad (gen 7)"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    // The hard floor. 320px is the original iPhone SE and still the narrowest
    // viewport in real use; anything that survives here survives anywhere.
    {
      name: "narrow",
      use: { ...devices["iPhone SE"], viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true },
    },
  ],
  webServer: {
    // `start`, not `dev`: the dev server's overlay and on-demand compilation
    // both change layout timing, and CI has already produced a build.
    command: `npm run start -- --port ${PORT}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
