import { expect, test } from "./fixtures/test";
import { scrollToEnd, scrollToTop, scrollToY } from "./fixtures/scroll";

/** The scroll helpers the specs share (see e2e/fixtures/scroll.ts for why they exist). */
test.describe("scroll helpers", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("the shared test turns smooth scrolling off, so a second scroll cannot be dropped", async ({
    page,
  }) => {
    const behavior = await page.evaluate(() => getComputedStyle(document.documentElement).scrollBehavior);

    expect(behavior).toBe("auto");
  });

  test("scrollToY lands exactly where it was told, at once", async ({ page }) => {
    await scrollToY(page, 700);

    expect(await page.evaluate(() => Math.round(window.scrollY))).toBe(700);
  });

  test("scrollToEnd reaches the bottom of a page that grows as it loads, and scrollToTop comes back", async ({
    page,
  }) => {
    await scrollToEnd(page);

    const atEnd = await page.evaluate(
      () => window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2,
    );
    expect(atEnd).toBe(true);

    await scrollToTop(page);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });

  test("two scrolls in a row both land (the second one used to be dropped under smooth scrolling)", async ({
    page,
  }) => {
    await scrollToEnd(page);
    await scrollToTop(page);
    await scrollToEnd(page);
    await scrollToTop(page);

    expect(await page.evaluate(() => window.scrollY)).toBe(0);
  });
});
