import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { bodyFor, mockApi } from "./fixtures/mock-api";

/** The encounter form's use of the patient's history: a read-only "last
 * reading" under every vital, and an autofill button that writes weight and
 * height into empty fields only. responsive.spec.ts already checks this page at
 * every width with the references on screen. */
test.describe("encounter vitals: last readings and autofill", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.goto("/encounters/e-001");
    await page.waitForLoadState("networkidle");
  });

  test("shows the last reading under each field, and says so when there is none", async ({ page }) => {
    await expect(page.getByText(/^Last: 132\/86 mmHg · /)).toBeVisible();
    await expect(page.getByText(/^Last: 64 bpm · /)).toBeVisible();
    await expect(page.getByText(/^Last: 36\.6 °C · /)).toBeVisible();
    // A pain score of 0 is a real answer, and has no unit.
    await expect(page.getByText(/^Last: 0 · /)).toBeVisible();
    // Oxygen saturation and respiratory rate have no earlier reading in the fixture.
    await expect(page.getByText("No previous reading")).toHaveCount(2);
  });

  test("the reference is text: it fills nothing and is not a control", async ({ page }) => {
    await page.getByText(/^Last: 64 bpm · /).click();

    // The fixture encounter already has a heart rate; the reference left it alone.
    await expect(page.getByLabel("Heart rate")).toHaveValue("58");
    await expect(page.getByRole("button", { name: /^Last:/ })).toHaveCount(0);
  });

  test("autofill writes weight and height into the empty fields, and nothing else", async ({ page }) => {
    let sent: { vitals: Record<string, number> } | undefined;
    await page.route("**/api/encounters/e-001", async (route) => {
      if (route.request().method() !== "PATCH") return route.fallback();
      sent = route.request().postDataJSON();
      const saved = { ...(bodyFor("/api/encounters/e-001") as object), vitals: sent!.vitals };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(saved) });
    });

    await expect(page.getByLabel("Weight")).toHaveValue("");
    // Before pressing it, the page says exactly what the button will do.
    await expect(page.getByText(/^Will copy weight 70\.5 kg \(visit of .+\) and height 164 cm \(visit of .+\)\.$/)).toBeVisible();
    await page.getByRole("button", { name: "Autofill weight & height" }).click();

    await expect(page.getByLabel("Weight")).toHaveValue("70.5");
    await expect(page.getByLabel("Height")).toHaveValue("164");

    // What was sent: the vitals already on the visit, plus exactly weight and height.
    expect(sent!.vitals).toEqual({ systolic: 158, diastolic: 94, heart_rate: 58, weight: 70.5, height: 164 });

    // Both fields are filled now, so there is nothing left to fill.
    await expect(page.getByText(/^Already filled: weight \(visit of .+\) and height \(visit of .+\)\.$/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Autofill weight & height" })).toBeDisabled();
  });
});
