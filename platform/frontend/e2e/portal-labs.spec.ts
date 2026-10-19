import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** The patient's "My labs": only what a clinician communicated, explained in
 * plain words. responsive.spec.ts checks the page at every width. */
test.describe("patient portal: my labs", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "patient");
    await mockApi(page);
    await page.goto("/portal/labs");
    await page.waitForLoadState("networkidle");
  });

  test("lists the communicated results with the value, the range and what it means for the number", async ({ page }) => {
    const items = page.getByRole("list").filter({ hasText: "Potassium" }).getByRole("listitem");

    await expect(items).toHaveCount(2);
    const potassium = items.first();
    await expect(potassium).toContainText("Potassium");
    await expect(potassium).toContainText("6.4");
    await expect(potassium).toContainText("Usual range");
    await expect(potassium).toContainText("Your Potassium needs attention soon");
    await expect(potassium).toContainText("Please call the clinic today");
    await expect(potassium.getByText("New")).toBeVisible();
    // The result that was already opened is not new.
    await expect(items.nth(1).getByText("New")).toHaveCount(0);
    await expect(items.nth(1)).toContainText("Your Sodium is within the usual range");
  });

  test("never shows the clinician's side of the review", async ({ page }) => {
    const text = (await page.locator("main").innerText()).toLowerCase();

    for (const hidden of ["disposition", "classification", "severity", "needs_patient_contact"]) {
      expect(text).not.toContain(hidden);
    }
  });

  test("is one tap away in the navigation, and a result opens in full", async ({ page }) => {
    await expect(page.getByRole("link", { name: "My Labs" }).first()).toBeVisible();

    await page.getByRole("link", { name: "Open this result" }).first().click();

    await expect(page).toHaveURL(/\/portal\/results\/rs-001$/);
    await expect(page.getByText("Your Potassium needs attention soon")).toBeVisible();
  });
});
