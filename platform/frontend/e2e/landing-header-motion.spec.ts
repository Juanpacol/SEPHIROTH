import { expect, test } from "./fixtures/test";
import { scrollToY } from "./fixtures/scroll";

/** The landing header: one bare header on the hero, a compact navy one that slides down once the
 * hero is behind you, and a single menu card that slides between menus. */
test.describe("header: hero and compact", () => {
  // The menus are buttons from 768 px up and one "Menu" button below it.
  const menuButton = (page: import("@playwright/test").Page) =>
    page.getByRole("button", { name: page.viewportSize()!.width < 768 ? "Menu" : "Product" });

  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("on the hero the header has no background of its own", async ({ page }) => {
    const hero = page.locator('[data-header="hero"]');

    await expect(hero).toBeVisible();
    await expect(hero).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(page.locator('[data-header="compact"]')).toBeHidden();
  });

  test("the hero header goes away with the hero, instead of following the reader", async ({ page }) => {
    const hero = page.locator('[data-header="hero"]');

    await scrollToY(page, 400);

    const box = await hero.boundingBox();
    expect(box!.y).toBeLessThan(-300);
  });

  test("past the hero a compact navy bar slides down, and only that header is reachable", async ({
    page,
  }) => {
    const compact = page.locator('[data-header="compact"]');

    await scrollToY(page, 2000);

    await expect(compact).toBeVisible();
    await expect.poll(async () => (await compact.boundingBox())!.y).toBe(0);
    await expect(compact).toHaveCSS("background-color", "rgba(18, 27, 44, 0.85)");
    // One menu button in the accessibility tree, not two.
    await expect(menuButton(page)).toHaveCount(1);
  });

  test("scrolling back to the top brings the bare header back and puts the bar away", async ({ page }) => {
    await scrollToY(page, 2000);
    await expect(page.locator('[data-header="compact"]')).toBeVisible();

    await scrollToY(page, 0);

    await expect(page.locator('[data-header="compact"]')).toBeHidden();
    await expect(menuButton(page)).toHaveCount(1);
  });

  test("the compact bar does not move the page", async ({ page }) => {
    const top = () =>
      page.locator("#features").evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
    const before = await top();

    await scrollToY(page, 2000);
    await page.waitForTimeout(500);

    expect(await top()).toBe(before);
  });
});

test.describe("header: menus", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(page.viewportSize()!.width < 768, "the menus are a bottom sheet on a phone");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("the card slides to the next menu instead of closing and opening another", async ({
    page,
    hasTouch,
  }) => {
    test.skip(hasTouch, "needs a pointer to move between menus");
    const card = page.locator("[data-nav-panel]");
    await page.getByRole("button", { name: "Product" }).click();
    await expect(card).toBeVisible();
    const first = await card.evaluate((el) => (el as HTMLElement).offsetLeft);
    await card.evaluate((el) => el.setAttribute("data-same", "1"));

    await page.getByRole("button", { name: "Open source" }).click();

    await expect(page.getByRole("region", { name: "Open source" })).toBeVisible();
    await expect(card).toHaveAttribute("data-same", "1");
    await expect
      .poll(() => card.evaluate((el) => (el as HTMLElement).offsetLeft))
      .toBeGreaterThan(first + 50);
  });

  test("the card is the header's own navy, and no pill or scrim is drawn", async ({ page }) => {
    await page.getByRole("button", { name: "Product" }).click();

    await expect(page.locator("[data-nav-panel]")).toHaveCSS("background-color", "rgb(18, 27, 44)");
    await expect(page.locator("[data-nav-pill], [data-nav-scrim]")).toHaveCount(0);
  });

  test("the line under a button grows on hover, and stays while its menu is open", async ({
    page,
    hasTouch,
  }) => {
    test.skip(hasTouch, "needs a pointer");
    const button = page.getByRole("button", { name: "For patients" });
    const line = () => button.evaluate((el) => getComputedStyle(el, "::after").transform);
    expect(await line()).toMatch(/matrix\(0,/);

    await button.hover();

    await expect.poll(line).toMatch(/matrix\(1,/);
  });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("the compact bar is simply there past the hero, and the menu opens", async ({ page }) => {
    test.skip(page.viewportSize()!.width < 768, "the menus are a bottom sheet on a phone");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await scrollToY(page, 2000);
    await expect(page.locator('[data-header="compact"]')).toBeVisible();

    await page.getByRole("button", { name: "Product" }).click();

    await expect(page.getByRole("region", { name: "Product" })).toBeVisible();
  });
});
