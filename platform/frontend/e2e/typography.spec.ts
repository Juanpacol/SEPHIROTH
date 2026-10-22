import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** The type system in a real browser: the display and mono fonts actually load, the
 * landing's headings and the app's labels use them, and nothing overflows at 320 px
 * or at the width a 200 % zoom leaves a desktop. The sources are pinned in
 * lib/__tests__/typography.test.ts. */
const loaded = (page: import("@playwright/test").Page, family: string) =>
  page.evaluate(
    (f) =>
      Array.from(document.fonts).some(
        (face) => face.family.toLowerCase().includes(f.toLowerCase()) && face.status === "loaded",
      ),
    family,
  );

test.describe("landing", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("the headline is set in the display font, and it loaded", async ({ page }) => {
    const h1 = page.getByRole("heading", { level: 1 });
    expect(await h1.evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/antonio/i);
    await expect.poll(() => loaded(page, "Antonio")).toBe(true);
  });

  test("section titles use the display font too", async ({ page }) => {
    const title = page.getByRole("heading", { level: 2 }).first();
    expect(await title.evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/antonio/i);
  });

  test("the headline fits the screen and reads large", async ({ page }) => {
    const h1 = page.getByRole("heading", { level: 1 });
    const box = await h1.boundingBox();
    const viewport = page.viewportSize()!;
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width + 1);
    const size = await h1.evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
    expect(size).toBeGreaterThanOrEqual(44);
    expect(size).toBeLessThanOrEqual(88);
  });

  test("the page does not overflow sideways", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("at the width a 200 % zoom leaves a desktop, nothing overflows either", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 800 });
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe("labels", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");
  });

  test("a group label in the navigation is mono, uppercase and at least 11 px", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "the sidebar is a drawer on a phone");
    const label = page.locator(".nav-group-label").first();
    const style = await label.evaluate((el) => {
      const s = getComputedStyle(el);
      return {
        family: s.fontFamily,
        transform: s.textTransform,
        size: parseFloat(s.fontSize),
        spacing: s.letterSpacing,
      };
    });
    expect(style.family).toMatch(/jetbrains/i);
    expect(style.transform).toBe("uppercase");
    expect(style.size).toBeGreaterThanOrEqual(11);
    expect(style.spacing).not.toBe("normal");
    await expect.poll(() => loaded(page, "JetBrains")).toBe(true);
  });

  test("the body text stays in the sans font", async ({ page }) => {
    const family = await page.locator("body").evaluate((el) => getComputedStyle(el).fontFamily);
    expect(family).toMatch(/manrope/i);
    expect(family).not.toMatch(/antonio/i);
  });

  test("the dashboard does not overflow sideways", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
