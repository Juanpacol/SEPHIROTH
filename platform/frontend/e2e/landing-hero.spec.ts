import { expect, test } from "./fixtures/test";

/** The landing hero: three full-height panels with the headline across them. The panels are the Ask,
 * Verify and Share cells of the feature grid; the data is pinned in
 * components/landing/__tests__/hero-triptych.test.tsx. */
test.describe("hero", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("has three panels with a caption each, and one headline across them", async ({ page }) => {
    const hero = page.locator("[data-hero]");

    await expect(hero.locator("[data-panel]")).toHaveCount(3);
    await expect(hero.getByRole("heading", { level: 1 })).toHaveCount(1);
    for (const id of ["ask", "verify", "share"])
      await expect(hero.locator(`[data-panel='${id}']`)).toBeAttached();
  });

  test("fills the first screen", async ({ page }) => {
    const hero = (await page.locator("[data-hero]").boundingBox())!;

    expect(hero.height).toBeGreaterThanOrEqual(Math.min(640, page.viewportSize()!.height) - 2);
    expect(hero.y).toBeLessThanOrEqual(1);
  });

  test("the headline's last words are set apart in the brand blue", async ({ page }) => {
    const words = page.getByRole("heading", { level: 1 }).locator("span");
    const count = await words.count();

    const colour = (i: number) => words.nth(i).evaluate((el) => getComputedStyle(el).color);
    expect(await colour(count - 1)).not.toBe(await colour(0));
    expect(await colour(count - 1)).toBe(await colour(count - 3));
  });

  test("pointing at a panel opens it, and clicking it does not close it again", async ({
    page,
    hasTouch,
  }) => {
    test.skip(hasTouch || page.viewportSize()!.width < 768, "panels open by hover from md up");
    const panel = page.locator("[data-panel='verify']");

    await panel.hover();
    await expect(panel).toHaveAttribute("data-open", "true");
    await panel.click();
    await page.waitForTimeout(400);

    await expect(panel).toHaveAttribute("data-open", "true");
  });

  test("tapping a panel opens it on a touch device, and tapping again closes it", async ({
    page,
    hasTouch,
  }) => {
    test.skip(!hasTouch, "needs a touch device");
    const panel = page.locator("[data-panel='share']");

    await panel.tap();
    await expect(panel).toHaveAttribute("data-open", "true");
    await panel.tap();
    await expect(panel).toHaveAttribute("data-open", "false");
  });

  test("opening a panel moves nothing below the hero", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "needs a pointer");
    const next = page.locator("#features");
    const top = () => next.evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
    const before = await top();

    for (const id of ["ask", "verify", "share"]) {
      await page.locator(`[data-panel='${id}']`).hover();
      await page.waitForTimeout(600);
      expect(Math.abs((await top()) - before)).toBeLessThanOrEqual(1);
    }
  });

  test("it fits the screen", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("the panels still open, with no spring to wait for", async ({ page, hasTouch }) => {
    test.skip(hasTouch || page.viewportSize()!.width < 768, "panels open by hover from md up");
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await page.locator("[data-panel='ask']").hover();

    await expect(page.locator("[data-panel='ask']")).toHaveAttribute("data-open", "true");
  });
});
