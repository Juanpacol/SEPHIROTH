import { expect, test } from "@playwright/test";

/** The "agents" section of the landing page shows the three agents that exist,
 * named by what they do. The copy itself is guarded in lib/__tests__/marketing-agents.test.ts. */
test.describe("landing: agents", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await page.locator("#agents").scrollIntoViewIfNeeded();
    await page.waitForTimeout(1000);
  });

  test("shows exactly the three agents, by what they do", async ({ page }) => {
    const section = page.locator("#agents");

    for (const name of ["Image Analysis", "Medication Interactions", "Guidelines & Literature"]) {
      await expect(section.getByText(name, { exact: true })).toHaveCount(1);
    }
    await expect(section.getByText(/Coordinator|Laboratory|Radiology|Drug Safety/)).toHaveCount(0);
  });

  test("the section fits the screen at every width", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("the hero walkthrough routes to one specialist out of three", async ({ page }) => {
    // The first stage is a tab panel whether or not autoplay has moved on from it.
    const stage = page.getByRole("tabpanel", { includeHidden: true }).first();

    for (const name of ["Guidelines & Literature", "Image Analysis", "Medication Interactions"]) {
      await expect(stage).toContainText(name);
    }
    await expect(stage).not.toContainText(/Laboratory|Coordinator/);
  });
});
