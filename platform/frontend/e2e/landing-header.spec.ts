import { expect, test } from "@playwright/test";

/** The landing header in a real browser: menus that lead somewhere, keyboard and touch
 * behaviour, and a header that says where you are. The data is pinned in
 * components/landing/__tests__/nav-menus.test.ts. */
test.describe("desktop menus", () => {
  // The menus show from 768 px (`md`); below that the header is a bottom sheet.
  test.beforeEach(async ({ page }) => {
    test.skip(page.viewportSize()!.width < 768, "the menus are a bottom sheet on a phone");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("each menu opens a panel of places, each with a line about what is there", async ({ page }) => {
    await page.getByRole("button", { name: "For patients" }).click();

    const panel = page.getByRole("region", { name: "For patients" });
    await expect(panel).toBeVisible();
    await expect(panel.getByRole("link", { name: /Set up your portal account/ })).toHaveAttribute(
      "href",
      "/portal/claim",
    );
    await expect(panel).toContainText("Use the claim code your clinician gave you.");
  });

  test("the open-source menu leaves the page, safely", async ({ page }) => {
    await page.getByRole("button", { name: "Open source" }).click();

    const repo = page.getByRole("region", { name: "Open source" }).getByRole("link", { name: /Repository/ });
    await expect(repo).toHaveAttribute("href", "https://github.com/Juanpacol/SEPHIROTH");
    await expect(repo).toHaveAttribute("target", "_blank");
    await expect(repo).toHaveAttribute("rel", "noopener noreferrer");
  });

  test("Escape closes a panel and returns the focus to its button", async ({ page }) => {
    const button = page.getByRole("button", { name: "Product" });
    await button.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "Product" })).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(page.locator("header").getByRole("region")).toHaveCount(0);
    await expect(button).toBeFocused();
  });

  test("Tab walks into the panel's links and out of it closes it", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "Safari on touch devices does not Tab to links");
    await page.getByRole("button", { name: "For patients" }).focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Tab");
    await expect(
      page.locator("header").getByRole("link", { name: /Set up your portal account/ }),
    ).toBeFocused();

    await page.getByRole("link", { name: "SEPHIROTH" }).focus();

    await expect(page.locator("header").getByRole("region")).toHaveCount(0);
  });

  test("a click elsewhere closes it, and choosing a section jumps there and closes it", async ({ page }) => {
    await page.getByRole("button", { name: "Product" }).click();
    await page
      .locator("header")
      .getByRole("link", { name: /Safeguards/ })
      .click();

    await expect(page.locator("header").getByRole("region")).toHaveCount(0);
    await expect(page).toHaveURL(/#safeguards$/);
  });

  test("the header says where you are: the section in view is marked in the Product menu", async ({
    page,
  }) => {
    // The reader is "in" a section while it crosses the middle of the screen.
    await page.locator("#faq").evaluate((el) => el.scrollIntoView({ block: "center" }));
    await page.waitForTimeout(900);

    await page.getByRole("button", { name: "Product" }).click();

    await expect(page.locator("header").getByRole("link", { name: /FAQ/ })).toHaveAttribute(
      "aria-current",
      "location",
    );
    await expect(page.getByRole("button", { name: "Product" })).toHaveAttribute("data-here", "true");
  });

  test("hovering opens a panel where the device can hover", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "no hover");
    await page.getByRole("button", { name: "Open source" }).hover();

    await expect(page.getByRole("region", { name: "Open source" })).toBeVisible();
  });

  test("the panel stays on screen and its links are tap-sized", async ({ page }) => {
    await page.getByRole("button", { name: "Open source" }).click();
    const panel = page.getByRole("region", { name: "Open source" });
    const box = (await panel.boundingBox())!;
    const viewport = page.viewportSize()!;

    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    for (const link of await panel.getByRole("link").all()) {
      expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  });
});

test.describe("phone", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(page.viewportSize()!.width >= 768, "desktop uses the menus");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("the sheet lists the same places, each with its line, grouped", async ({ page }) => {
    await page.getByRole("button", { name: "Menu" }).click();

    const sheet = page.getByRole("dialog");
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("navigation", { name: "For patients" })).toContainText(
      "Set up your portal account",
    );
    await expect(sheet.getByRole("navigation", { name: "Open source" })).toContainText("Documentation");
    await expect(sheet.getByRole("navigation", { name: "Product" })).toContainText(
      "Five steps from a question",
    );
  });

  test("choosing a place closes the sheet", async ({ page }) => {
    await page.getByRole("button", { name: "Menu" }).click();

    await page
      .getByRole("dialog")
      .getByRole("link", { name: /How it works/ })
      .click();

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page).toHaveURL(/#how-it-works$/);
  });
});

test("the header never overflows the screen", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
