import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** A patient's lab card links here with the patient and the list already
 * chosen. */
test.describe("results inbox opened from a link", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
  });

  test("starts on the patient and the list in the link", async ({ page }) => {
    await page.goto("/results?patient=p-001&filter=closed");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("tab", { name: "Closed" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("select", { hasText: "All patients" })).toHaveValue("p-001");
  });

  test("without a link it starts on the open list and every patient", async ({ page }) => {
    await page.goto("/results");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("tab", { name: "Open" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("select", { hasText: "All patients" })).toHaveValue("");
  });

  test("ignores a list name it does not know", async ({ page }) => {
    await page.goto("/results?filter=nonsense");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("tab", { name: "Open" })).toHaveAttribute("aria-selected", "true");
  });
});
