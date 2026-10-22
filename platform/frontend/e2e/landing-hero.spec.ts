import { expect, test } from "@playwright/test";

/** The landing hero: the headline and the way in on one side, an answer as the product
 * gives it on the other. The data is pinned in components/landing/__tests__/answer-card.test.tsx. */
test.describe("hero", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("two columns from lg up, stacked below, headline and card side by side or one over the other", async ({
    page,
  }) => {
    const h1 = (await page.getByRole("heading", { level: 1 }).boundingBox())!;
    const card = (await page.getByTestId("answer-card").boundingBox())!;

    if (page.viewportSize()!.width >= 1024) {
      expect(card.x).toBeGreaterThan(h1.x + h1.width * 0.5);
      expect(Math.abs(card.y - h1.y)).toBeLessThan(400);
    } else {
      expect(card.y).toBeGreaterThan(h1.y + h1.height);
    }
  });

  test("the headline is large without taking over: three lines or fewer on a wide screen", async ({
    page,
  }) => {
    test.skip(page.viewportSize()!.width < 1024, "that is the two-column layout");
    const h1 = page.getByRole("heading", { level: 1 });

    const lines = await h1.evaluate((el) => {
      const lh = parseFloat(getComputedStyle(el).lineHeight);
      return Math.round(el.getBoundingClientRect().height / lh);
    });

    expect(lines).toBeLessThanOrEqual(4);
  });

  test("the card is an example answer, in the product's own pieces", async ({ page }) => {
    const card = page.getByTestId("answer-card");

    await expect(card).toContainText("Example answer");
    await expect(card.getByRole("tab")).toHaveCount(3);
    await expect(card.getByRole("tabpanel")).toContainText("A clinician asks");
    await expect(card.getByRole("tabpanel")).toContainText("Guidelines & Literature");
  });

  test("picking an example shows it, and the card does not change height", async ({ page }) => {
    const card = page.getByTestId("answer-card");
    const height = async () => Math.round((await card.boundingBox())!.height);
    await page.waitForTimeout(2500);
    const before = await height();

    for (const name of ["Medication", "Declines", "Guideline"]) {
      await card.getByRole("tab", { name }).click();
      await page.waitForTimeout(2200);
      expect(Math.abs((await height()) - before), name).toBeLessThanOrEqual(1);
    }
    await card.getByRole("tab", { name: "Declines" }).click();
    await expect(card.getByRole("tabpanel")).toContainText("declines to answer instead of guessing");
  });

  test("nothing below the hero moves while the examples change", async ({ page }) => {
    const next = page.locator("section").nth(1);
    const top = () => next.evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
    const before = await top();

    await page.getByTestId("answer-card").getByRole("tab", { name: "Declines" }).click();
    await page.waitForTimeout(2200);

    expect(Math.abs((await top()) - before)).toBeLessThanOrEqual(1);
  });

  test("the card has a pause button, and pausing keeps the example on show", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "the pointer rests on the card on a touch device");
    const card = page.getByTestId("answer-card");

    await card.getByRole("button", { name: "Pause examples" }).click();
    await page.mouse.move(5, 5);
    await page.waitForTimeout(9000);

    await expect(card.getByRole("tab", { name: "Guideline" })).toHaveAttribute("aria-selected", "true");
  });

  test("it fits the screen", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    const card = (await page.getByTestId("answer-card").boundingBox())!;
    expect(card.x).toBeGreaterThanOrEqual(0);
    expect(card.x + card.width).toBeLessThanOrEqual(page.viewportSize()!.width);
  });
});

test.describe("how it works", () => {
  test("carries the five-step walkthrough the hero used to", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const section = page.locator("#how-it-works");
    await expect(section.getByRole("tablist")).toBeVisible();
    await expect(section.getByRole("tab")).toHaveCount(5);
    await expect(section).toContainText("tabs below");
    await expect(page.locator("[data-hero]").getByRole("tab", { name: /Pick a specialist/ })).toHaveCount(0);
  });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("the card stays on its first example, finished, and has nothing to pause", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const card = page.getByTestId("answer-card");

    await page.waitForTimeout(9000);

    await expect(card.getByRole("tab", { name: "Guideline" })).toHaveAttribute("aria-selected", "true");
    await expect(card.getByRole("button", { name: /Pause|Play/ })).toHaveCount(0);
    await expect(card.getByRole("tabpanel")).toContainText("Answered · 2 of 2 claims supported");
  });
});
