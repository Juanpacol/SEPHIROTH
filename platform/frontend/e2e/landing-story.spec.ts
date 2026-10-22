import { expect, test } from "./fixtures/test";
import { scrollToEnd } from "./fixtures/scroll";

/** The two Apple-style pieces of the landing page: the "how it works" story that changes as you
 * scroll, and the row of safeguard cards you move through sideways. */
test.describe("how it works: the story", () => {
  test("the panel follows the step in the middle of the screen", async ({ page, isMobile }) => {
    test.skip(
      isMobile || (page.viewportSize()?.width ?? 0) < 1024,
      "below lg each step carries its own panel",
    );
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const panel = page.locator("[data-story-panel]");
    const visibleStage = () =>
      panel.evaluate((el) => {
        const stages = Array.from(el.querySelectorAll(":scope > div > div"));
        return stages.findIndex((s) => getComputedStyle(s).opacity === "1");
      });

    const steps = page.locator("#how-it-works ol > li");
    await steps.nth(0).evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expect.poll(visibleStage).toBe(0);

    await steps.nth(3).evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expect.poll(visibleStage).toBe(3);
  });

  test("the panel stays in view while the steps go by", async ({ page, isMobile }) => {
    test.skip(
      isMobile || (page.viewportSize()?.width ?? 0) < 1024,
      "below lg each step carries its own panel",
    );
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page
      .locator("#how-it-works ol > li")
      .nth(1)
      .evaluate((el) => el.scrollIntoView({ block: "center" }));
    await page.waitForTimeout(500);

    const box = await page.locator("[data-story-panel]").boundingBox();

    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  });

  test("on a phone every step carries its own panel", async ({ page }) => {
    test.skip((page.viewportSize()?.width ?? 0) >= 1024, "the sticky panel is the shape from lg up");
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("[data-story-panel]")).toBeHidden();
    const first = page.locator("#how-it-works ol > li").first();
    await first.scrollIntoViewIfNeeded();
    await expect(first.locator("div.rounded-\\[28px\\]")).toBeVisible();
  });
});

test.describe("safeguards: the cards", () => {
  test("the arrows move to the next card and back", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "a touch screen swipes; the arrows are for a mouse");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const section = page.locator("#safeguards");
    await section.scrollIntoViewIfNeeded();
    const track = section.getByRole("list").first();
    const left = () => track.evaluate((el) => Math.round(el.scrollLeft));
    const previous = section.getByRole("button", { name: "Previous" });
    const next = section.getByRole("button", { name: "Next" });

    await expect(previous).toBeDisabled();
    await next.click();

    await expect.poll(left).toBeGreaterThan(100);
    await expect(previous).toBeEnabled();
    await previous.click();
    await expect.poll(left).toBe(0);
  });

  test("each card carries something to try, and the page does not scroll sideways", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await scrollToEnd(page);

    for (const id of ["citations", "claims", "abstain"])
      await expect(page.locator(`[data-trust-card="${id}"]`)).toBeAttached();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
