import { expect, test } from "./fixtures/test";

/** The landing's entrance effects: blocks below the fold come in as they are scrolled to, without ever
 * moving the page, and not at all for a reader who asked for reduced motion. */
test.describe("entrance effects", () => {
  test("a block below the fold starts held back and comes in when it is scrolled to", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const faq = page.locator("#faq details").first().locator("..");

    await expect(faq).toHaveAttribute("data-reveal", "hidden");
    await faq.evaluate((el) => el.scrollIntoView({ block: "center" }));

    await expect(faq).toHaveAttribute("data-reveal", "shown");
    await expect.poll(() => faq.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");
  });

  test("the hero is never held back", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("[data-hero] [data-reveal='hidden']")).toHaveCount(0);
  });

  test("coming in moves nothing: the sections keep their places", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const top = () =>
      page.locator("#faq").evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
    const before = await top();

    await page.locator("#how-it-works").evaluate((el) => el.scrollIntoView({ block: "start" }));
    await page.waitForTimeout(1500);

    expect(await top()).toBe(before);
  });

  test("a heading's words come in one after another", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const heading = page.locator("#faq h2");

    await expect(heading).toHaveAttribute("data-reveal", "hidden");
    await heading.evaluate((el) => el.scrollIntoView({ block: "center" }));

    await expect(heading).toHaveAttribute("data-reveal", "shown");
    await expect(heading.locator("span").first()).toHaveCSS("opacity", "1");
  });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("nothing is held back", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("[data-reveal='hidden']")).toHaveCount(0);
  });
});
