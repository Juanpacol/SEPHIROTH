import { expect, test } from "@playwright/test";
import { seedAuth, type Role } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** Two assertions, every route, every viewport: nothing spills sideways, and
 * nothing is too small to tap. Routes join this matrix as their phase lands. */

export const ROUTES: { path: string; role: Role | null }[] = [
  { path: "/", role: null },
  { path: "/login", role: null },
  { path: "/portal/claim", role: null },
  { path: "/dashboard", role: "clinician" },
  { path: "/patients", role: "clinician" },
  { path: "/patients/p-001", role: "clinician" },
  { path: "/alerts", role: "clinician" },
  { path: "/approvals", role: "clinician" },
  { path: "/encounters/e-001", role: "clinician" },
  { path: "/results", role: "clinician" },
  { path: "/schedule", role: "clinician" },
  { path: "/imaging", role: "clinician" },
  { path: "/evidence", role: "clinician" },
  { path: "/profile", role: "clinician" },
  { path: "/preferences", role: "clinician" },
  { path: "/portal", role: "patient" },
  { path: "/portal/appointments", role: "patient" },
  { path: "/portal/results", role: "patient" },
  { path: "/portal/results/rs-001", role: "patient" },
];

for (const route of ROUTES) {
  test.describe(route.path, () => {
    test.beforeEach(async ({ page }) => {
      if (route.role) await seedAuth(page, route.role);
      await mockApi(page);
      await page.goto(route.path);
      await expect(page.locator("body")).toBeVisible();
      // React Query settles one tick after mount; without this the assertions
      // can run against a skeleton, which fits everywhere.
      await page.waitForLoadState("networkidle");
    });

    test("nothing overflows horizontally", async ({ page }) => {
      const offenders = await page.evaluate(() => {
        const docWidth = document.documentElement.clientWidth;

        // A child wider than its own scroller is a design decision, not a bug:
        // the week grid and the segmented control both scroll on purpose. Only
        // what escapes the *document* counts, so walk up looking for a scroller
        // before blaming an element.
        const insideScroller = (el: Element): boolean => {
          for (let p = el.parentElement; p; p = p.parentElement) {
            const overflowX = getComputedStyle(p).overflowX;
            if (overflowX === "auto" || overflowX === "scroll" || overflowX === "hidden") return true;
          }
          return false;
        };

        return Array.from(document.querySelectorAll<HTMLElement>("body *"))
          .filter((el) => {
            const box = el.getBoundingClientRect();
            if (box.width === 0 || box.height === 0) return false;
            if (insideScroller(el)) return false;
            return box.right > docWidth + 1 || box.left < -1;
          })
          .slice(0, 8)
          .map((el) => `<${el.tagName.toLowerCase()} class="${el.className}">`.slice(0, 140));
      });
      expect(offenders, `elements escaping the viewport on ${route.path}`).toEqual([]);

      const documentScrolls = await page.evaluate(
        () => document.scrollingElement!.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(documentScrolls, `${route.path} scrolls sideways`).toBe(false);
    });

    test("touch targets are at least 44px", async ({ page }, testInfo) => {
      // Runs on one phone project only: the same controls at the same sizes on
      // a second narrow viewport would just double the failure noise.
      test.skip(testInfo.project.name !== "iphone-14", "Touch sizing is a phone concern.");

      const tooSmall = await page.$$eval(
        'a, button, [role="button"], input:not([type="hidden"]), select, summary',
        (els) =>
          els
            .filter((el) => {
              const box = el.getBoundingClientRect();
              if (box.width === 0 || box.height === 0) return false;
              if (getComputedStyle(el).visibility === "hidden") return false;
              // Escape hatch for links inside prose and other genuinely inline
              // targets. Every use has to justify itself in review.
              if (el.closest("[data-tap-exempt]")) return false;
              // AND, not OR: an inline link in a paragraph is wide and short by
              // nature, and flagging those drowns out the real offenders.
              return box.height < 44 && box.width < 44;
            })
            .slice(0, 8)
            .map((el) => `<${el.tagName.toLowerCase()}> "${el.textContent?.trim().slice(0, 30) ?? ""}"`),
      );
      expect(tooSmall, `controls under 44px on ${route.path}`).toEqual([]);
    });
  });
}
