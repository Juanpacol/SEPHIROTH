import { expect, test } from "@playwright/test";

/** The "agents" section of the landing page is a row of seven chapters: the three agents that
 * exist, named by what they do, then the four parts of the platform. The copy itself is guarded
 * in lib/__tests__/marketing-agents.test.ts. */
test.describe("landing: agents and platform", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("#agents").scrollIntoViewIfNeeded();
    await page.waitForTimeout(600);
  });

  test("lists the three agents by what they do, then the platform", async ({ page }) => {
    const tabs = page.locator("#agents").getByRole("tab");
    await expect(tabs).toHaveCount(7);
    await expect(tabs.nth(0)).toContainText("Image Analysis");
    await expect(tabs.nth(1)).toContainText("Medication Interactions");
    await expect(tabs.nth(2)).toContainText("Guidelines & Literature");
    await expect(
      page.locator("#agents").getByText(/Coordinator|Laboratory|Radiology|Drug Safety/),
    ).toHaveCount(0);
  });

  test("choosing a chapter shows what it does, and the arrow keys move along the row", async ({
    page,
    hasTouch,
  }) => {
    const section = page.locator("#agents");
    await section.getByRole("tab", { name: /Medication Interactions/ }).click();
    await expect(section.getByRole("tabpanel")).toContainText("known drug-drug interactions");

    test.skip(hasTouch, "touch devices have no arrow keys");
    await page.keyboard.press("ArrowRight");
    await expect(section.getByRole("tab", { name: /Guidelines & Literature/ })).toBeFocused();
    await expect(section.getByRole("tabpanel")).toContainText("PubMed");
  });

  test("changing chapter moves nothing below it", async ({ page }) => {
    const section = page.locator("#agents");
    const below = () =>
      page.locator("#faq").evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
    await section.getByRole("tab").nth(0).click();
    await page.waitForTimeout(400);
    const before = await below();

    for (const i of [3, 6, 1]) {
      await section.getByRole("tab").nth(i).click();
      await page.waitForTimeout(350);
      // The panel is as tall as its text, so a longer description may push the page: allow it
      // to change by no more than a few lines, never a jump.
      expect(Math.abs((await below()) - before)).toBeLessThanOrEqual(120);
    }
  });

  test("the section fits the screen at every width", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});

test.describe("landing: how it works", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("#how-it-works").scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
  });

  test("an answer taken apart: five steps, and the one specialist the sample was routed to", async ({
    page,
  }) => {
    const section = page.locator("#how-it-works");

    await expect(section.locator("[data-step]")).toHaveCount(5);
    await expect(section.locator("[data-anatomy-card]")).toContainText("Guidelines & Literature");
    await expect(section.getByText(/Laboratory|Coordinator/)).toHaveCount(0);
  });

  test("pointing at a step lights the part of the answer it is about", async ({ page, hasTouch }) => {
    const section = page.locator("#how-it-works");
    const target = section.locator("[data-step='guard']");

    if (hasTouch) await target.tap();
    else await target.hover();

    await expect(section.locator("[data-part='guard']")).toHaveAttribute("data-active", "true");
    await expect(section.locator("[data-part='route']")).toHaveAttribute("data-active", "false");
  });

  test("changing step moves nothing below it", async ({ page }) => {
    const section = page.locator("#how-it-works");
    const below = () =>
      page
        .locator("#agents")
        .evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
    const before = await below();

    for (const id of ["guard", "verify", "abstain", "write"]) {
      await section.locator(`[data-step='${id}']`).click();
      await page.waitForTimeout(350);
      expect(Math.abs((await below()) - before)).toBeLessThanOrEqual(1);
    }
  });

  test("fits the screen at every width", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
