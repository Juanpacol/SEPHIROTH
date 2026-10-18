import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** The patient timeline folds to the 5 most recent events; the fixture has 10.
 * responsive.spec.ts checks the folded page at every width — this covers the
 * toggle itself, and that the unfolded history still fits the screen. */
test.describe("patient timeline fold", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.goto("/patients/p-001");
    await page.waitForLoadState("networkidle");
  });

  test("shows the 5 most recent events and unfolds the rest in place", async ({ page }) => {
    const toggle = page.getByRole("button", { name: "Show 5 earlier events" });
    await expect(toggle).toBeVisible();

    const listId = await toggle.getAttribute("aria-controls");
    const events = page.locator(`[id="${listId}"] > li`);
    await expect(events).toHaveCount(5);
    await expect(events.last()).toContainText("Comprehensive metabolic panel");

    const url = page.url();
    await toggle.click();
    await expect(events).toHaveCount(10);
    await expect(events.first()).toContainText("Type 2 diabetes mellitus diagnosed");
    expect(page.url()).toBe(url);

    const less = page.getByRole("button", { name: "Show less" });
    await expect(less).toHaveAttribute("aria-expanded", "true");

    const scrollsSideways = await page.evaluate(
      () => document.scrollingElement!.scrollWidth > document.documentElement.clientWidth + 1,
    );
    expect(scrollsSideways, "the unfolded timeline scrolls sideways").toBe(false);

    await less.click();
    await expect(events).toHaveCount(5);
    await expect(page.getByRole("button", { name: "Show 5 earlier events" })).toBeVisible();
  });
});
