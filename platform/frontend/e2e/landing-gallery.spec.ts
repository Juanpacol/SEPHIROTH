import { expect, test } from "@playwright/test";

/** The imaging gallery on the landing page ("Every modality, one imaging
 * pipeline"). The projects in playwright.config.ts include touch devices and a
 * desktop, so each test asks the browser what it can do rather than assuming. */
test.describe("landing: imaging gallery", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const heading = page.getByText("Every modality, one imaging pipeline");
    await heading.scrollIntoViewIfNeeded();
    // Past the entrance animation.
    await page.waitForTimeout(2000);
  });

  /** The ten cards, and only them: other parts of the landing page have groups too. */
  const cards = (page: import("@playwright/test").Page) =>
    page
      .getByText("Every modality, one imaging pipeline")
      .locator("xpath=ancestor::section[1]")
      .getByRole("group");

  test("every card has its title and caption in the page, ten of them", async ({ page }) => {
    await expect(cards(page)).toHaveCount(10);
    await expect(cards(page).first().locator("p")).toHaveCount(2);
  });

  test("on a device that cannot hover, captions are visible without touching anything", async ({ page }) => {
    const canHover = await page.evaluate(() => matchMedia("(hover: hover)").matches);
    test.skip(canHover, "this project has a pointer");

    const opacities = await page
      .locator("[class*=caption]")
      .evaluateAll((els) => els.filter((e) => e.className.includes("caption") && !e.className.includes("Title") && !e.className.includes("Text")).map((e) => getComputedStyle(e).opacity));
    expect(opacities).toHaveLength(10);
    expect(new Set(opacities)).toEqual(new Set(["1"]));
  });

  test("with a pointer, a caption waits for hover or keyboard focus", async ({ page }) => {
    const canHover = await page.evaluate(() => matchMedia("(hover: hover)").matches);
    test.skip(!canHover, "this project has no pointer");

    const first = cards(page).first();
    const caption = first.locator("[class*=caption]").first();
    await expect(caption).toHaveCSS("opacity", "0");

    await first.focus();
    await expect(caption).toHaveCSS("opacity", "1");
    await expect(first.locator("[class*=itemImg]")).toHaveCSS("outline-style", "solid");
  });

  test("a card is reachable with the keyboard", async ({ page }) => {
    const canHover = await page.evaluate(() => matchMedia("(hover: hover)").matches);
    test.skip(!canHover, "keyboard focus is a desktop path here");

    const first = cards(page).first();
    await first.focus();
    await page.keyboard.press("Tab");

    await expect(cards(page).nth(1)).toBeFocused();
  });

  test("a card that goes nowhere does not look like a link, and nothing is promoted permanently", async ({ page }) => {
    const first = cards(page).first();

    await expect(first).toHaveCSS("cursor", "default");
    await expect(first).not.toHaveCSS("will-change", /transform/);
  });

  test("every image has a light edge and a layered shadow", async ({ page }) => {
    const img = cards(page).first().locator("[class*=itemImg]");

    const shadow = await img.evaluate((el) => getComputedStyle(el).boxShadow);
    expect(shadow.split("rgba(").length - 1).toBeGreaterThanOrEqual(3);
    const edge = await img.evaluate((el) => getComputedStyle(el, "::after").boxShadow);
    expect(edge).toContain("inset");
    expect(edge).toContain("255, 255, 255");
  });

  test("the gallery does not overflow the page", async ({ page }) => {
    const overflows = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);

    expect(overflows).toBe(false);
  });
});
