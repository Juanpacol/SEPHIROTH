import { expect, test as base } from "@playwright/test";

/** `test` for specs that scroll. The same as Playwright's, with smooth scrolling turned off
 * on every page (see `./scroll.ts` for why). Import it instead of `@playwright/test`:
 *
 *     import { expect, test } from "./fixtures/test";
 *
 * It changes nothing else: animations, hover and reduced-motion behave as in the app. */
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.addInitScript(() => {
      document.addEventListener("DOMContentLoaded", () => {
        const style = document.createElement("style");
        style.textContent = "html { scroll-behavior: auto !important; }";
        document.head.appendChild(style);
      });
    });
    await use(page);
  },
});

export { expect };
