import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** Telling the patient about a result, from the inbox. The routes below stand in
 * for the endpoint; the backend side is tested in tests/test_inform_patient.py. */
test.describe("inform the patient from the results inbox", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.goto("/results");
    await page.waitForLoadState("networkidle");
  });

  test("opens a panel instead of leaving the page, with the result and a suggested message", async ({ page }) => {
    await page.getByRole("button", { name: "Tell the patient" }).click();

    const panel = page.getByRole("dialog");
    await expect(panel).toBeVisible();
    await expect(page).toHaveURL(/\/results$/);
    await expect(panel.getByText("Potassium", { exact: true })).toBeVisible();
    await expect(panel.getByLabel("Message to the patient")).toHaveValue(/result for Potassium: 6\.4 mmol\/L/);
  });

  test("sends what was written, then closes and says the patient was notified", async ({ page }) => {
    let sent: Record<string, unknown> | undefined;
    await page.route("**/api/results/reviews/rr-1/communicate", async (route) => {
      sent = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: "rr-1", status: "communicated", patient_notified: true }),
      });
    });
    await page.getByRole("button", { name: "Tell the patient" }).click();
    await page.getByLabel("Message to the patient").fill("Please call the clinic today.");

    await page.getByRole("button", { name: "Send to the patient" }).click();

    await expect(page.getByText("The patient has been told and notified.")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    // Exactly the message: no timeline entry is named, so the server makes one.
    expect(sent).toEqual({ message: "Please call the clinic today." });
  });

  test("keeps the panel open and explains a conflict", async ({ page }) => {
    await page.route("**/api/results/reviews/rr-1/communicate", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "This result has already been communicated" }),
      }),
    );
    await page.getByRole("button", { name: "Tell the patient" }).click();

    await page.getByRole("button", { name: "Send to the patient" }).click();

    await expect(page.getByRole("dialog").getByRole("alert")).toContainText("already told");
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("fits the screen and its buttons are touch-sized", async ({ page }) => {
    await page.getByRole("button", { name: "Tell the patient" }).click();
    const panel = page.getByRole("dialog");
    await expect(panel).toBeVisible();
    // Measure at rest: the panel slides in a few pixels, and mid-slide it overhangs.
    await page.evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((a) => Number.isFinite(a.effect?.getComputedTiming().endTime as number))
          .map((a) => a.finished.catch(() => undefined)),
      ),
    );

    const fits = await panel.evaluate((el) => el.scrollWidth <= el.clientWidth + 1);
    expect(fits).toBe(true);
    for (const name of ["Send to the patient", "Cancel"]) {
      const box = await panel.getByRole("button", { name }).boundingBox();
      expect(Math.max(box!.width, box!.height)).toBeGreaterThanOrEqual(44);
    }
  });
});
