import { expect, test } from "./fixtures/test";
import { scrollToEnd } from "./fixtures/scroll";

/** The row of safeguard cards you move through sideways, in the manner of Apple's product pages. */
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
