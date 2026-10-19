import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** The patient's lab card: one card, one row per test, most urgent first.
 * responsive.spec.ts checks this page at every width; this checks what is on it. */
test.describe("patient lab card", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.goto("/patients/p-001");
    await page.waitForLoadState("networkidle");
  });

  test("is a single card, with the worst result first and a status in words", async ({ page }) => {
    const card = page.getByTestId("labs-card");
    await expect(card).toBeVisible();
    // The two cards this replaced are gone.
    await expect(page.getByRole("heading", { name: "Lab Trend" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Lab Results" })).toHaveCount(0);

    const rows = card.getByRole("listitem");
    await expect(rows.first()).toContainText("Potassium");
    await expect(rows.first()).toContainText("6.4 mmol/L");
    await expect(rows.first()).toContainText("Critical");
    await expect(rows.first()).toContainText("Reference 3.5–5.1 mmol/L");
    await expect(rows.first()).toContainText("3 readings");
  });

  test("says high or low, not only abnormal, and leaves blood pressure out", async ({ page }) => {
    const card = page.getByTestId("labs-card");

    await expect(card.getByRole("listitem").filter({ hasText: "LDL" })).toContainText("High");
    await expect(card.getByRole("listitem").filter({ hasText: "Sodium" })).toContainText("Normal");
    await expect(card.getByText(/Blood pressure|Systolic/)).toHaveCount(0);
  });

  test("keeps a test that only the snapshot has, and says it has no history", async ({ page }) => {
    const row = page.getByTestId("labs-card").getByRole("listitem").filter({ hasText: "Creatinine" });

    await expect(row).toContainText("2.1 mg/dL");
    await expect(row).toContainText("No history");
    await expect(row.getByText(/Critical|High|Low|Normal/)).toHaveCount(0);
  });

  test("shows each test once", async ({ page }) => {
    await expect(page.getByTestId("labs-card").getByText("Potassium")).toHaveCount(1);
  });

  test("shows where each result is in its review, and nothing for one with no review", async ({ page }) => {
    const card = page.getByTestId("labs-card");

    const potassium = card.getByRole("listitem").filter({ hasText: "Potassium" });
    await expect(potassium.getByTestId("lab-review")).toContainText("Patient told");
    await expect(potassium.getByTestId("lab-review")).toContainText("The patient needs to be told");
    await expect(potassium.getByTestId("lab-review")).toContainText("Dr. Ana Ruiz");
    await expect(card.getByRole("listitem").filter({ hasText: "LDL" }).getByTestId("lab-review")).toContainText(
      "Not reviewed",
    );
    // Sodium has no review: no state, and not the words "not reviewed" either.
    await expect(card.getByRole("listitem").filter({ hasText: "Sodium" }).getByTestId("lab-review")).toHaveCount(0);
  });

  test("the link opens the results inbox on that patient", async ({ page }) => {
    await page.getByTestId("labs-card").getByRole("link", { name: "Open in results" }).first().click();

    await expect(page).toHaveURL(/\/results\?patient=p-001&filter=open$/);
    await expect(page.getByRole("heading", { name: "Results", level: 1 })).toBeVisible();
  });
});
