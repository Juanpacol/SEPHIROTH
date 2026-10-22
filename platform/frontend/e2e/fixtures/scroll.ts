import type { Page } from "@playwright/test";

/** Scrolling helpers for the specs.
 *
 * The site scrolls smoothly (`scroll-behavior: smooth` for anyone who has not asked for less
 * motion). A second `scrollTo` while a smooth scroll is still running can be dropped in
 * WebKit, and a "scroll to the end" that goes before the pictures further up have loaded
 * lands short, because the page grows as they arrive. Both made specs fail now and then for
 * reasons that had nothing to do with what they test. These two helpers remove them: the
 * `test` in `./test.ts` turns smooth scrolling off, and `scrollToEnd` keeps going until the
 * page has stopped growing. */

/** Jumps to the very end of the page, repeating while pictures loading above make it taller. */
export async function scrollToEnd(page: Page): Promise<void> {
  let last = -1;
  for (let i = 0; i < 20; i++) {
    const height = await page.evaluate(() => {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" });
      return document.documentElement.scrollHeight;
    });
    if (height === last) return;
    last = height;
    await page.waitForTimeout(150);
  }
}

/** Jumps to the top of the page. */
export async function scrollToTop(page: Page): Promise<void> {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
}

/** Jumps to a given offset. */
export async function scrollToY(page: Page, top: number): Promise<void> {
  await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), top);
}
