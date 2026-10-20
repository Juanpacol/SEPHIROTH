import { expect, test, type Page } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** Recording a lab result from the patient chart. The routes below stand in for
 * the endpoints; the backend side is tested in tests/test_record_lab_form.py. */
const CATALOG = {
  tests: [
    {
      test_name: "potassium",
      unit: "mEq/L",
      reference_low: 3.5,
      reference_high: 5.1,
      plausible_low: 0.5,
      plausible_high: 12,
    },
    {
      test_name: "hba1c",
      unit: "%",
      reference_low: 4,
      reference_high: 5.6,
      plausible_low: 2,
      plausible_high: 20,
    },
  ],
};

const json = (body: unknown, status = 200) => ({
  status,
  contentType: "application/json",
  body: JSON.stringify(body),
});

async function open(page: Page) {
  await seedAuth(page, "clinician");
  await mockApi(page);
  await page.route("**/api/results/labs/catalog", (r) => r.fulfill(json(CATALOG)));
  await page.route("**/api/results/labs/preview", async (r) => {
    const { value } = r.request().postDataJSON();
    if (value > 12) {
      return r.fulfill(
        json(
          {
            detail: [
              {
                msg: "Value error, 62 is outside what potassium can measure (0.5-12.0).",
              },
            ],
          },
          422,
        ),
      );
    }
    return r.fulfill(
      json(
        value >= 6
          ? {
              severity: "critical",
              reason: "Potassium 6.5 is above the critical limit of 6.0.",
              reference_low: 3.5,
              reference_high: 5.1,
            }
          : {
              severity: "normal",
              reason: "Within 3.5-5.1.",
              reference_low: 3.5,
              reference_high: 5.1,
            },
      ),
    );
  });
  await page.goto("/patients/p-001");
  await page.waitForLoadState("networkidle");
  await page.getByRole("button", { name: "Record result" }).click();
}

test.describe("record a lab result", () => {
  test("choosing a test fills the unit and the range, and both can be edited", async ({ page }) => {
    await open(page);
    const panel = page.getByRole("dialog");

    await panel.getByLabel("Test").selectOption("potassium");

    await expect(panel.getByLabel("Unit")).toHaveValue("mEq/L");
    await expect(panel.getByLabel("Reference low")).toHaveValue("3.5");
    await expect(panel.getByLabel("Reference high")).toHaveValue("5.1");
    await panel.getByLabel("Reference high").fill("5.5");
    await expect(panel.getByLabel("Reference high")).toHaveValue("5.5");
  });

  test("shows the classification and its reason before anything is saved", async ({ page }) => {
    await open(page);
    const panel = page.getByRole("dialog");
    await panel.getByLabel("Test").selectOption("potassium");
    await expect(panel.getByRole("button", { name: "Save result" })).toBeDisabled();

    await panel.getByLabel("Value").fill("6.5");

    const preview = panel.getByTestId("record-lab-preview");
    await expect(preview).toContainText("Critical");
    await expect(preview).toContainText("above the critical limit");
    await expect(panel.getByRole("button", { name: "Save result" })).toBeEnabled();
  });

  test("refuses an impossible value with the server's reason and cannot be saved", async ({ page }) => {
    await open(page);
    const panel = page.getByRole("dialog");
    await panel.getByLabel("Test").selectOption("potassium");

    await panel.getByLabel("Value").fill("62");

    await expect(panel.getByTestId("record-lab-preview")).toContainText("outside what potassium can measure");
    await expect(panel.getByRole("button", { name: "Save result" })).toBeDisabled();
  });

  test("saves exactly what was entered, then closes and reloads the labs card", async ({ page }) => {
    await open(page);
    let sent: Record<string, unknown> | undefined;
    let historyLoads = 0;
    await page.route("**/api/patients/p-001/labs", (r) => {
      historyLoads += 1;
      return r.fallback();
    });
    await page.route("**/api/results/labs", async (r) => {
      sent = r.request().postDataJSON();
      await r.fulfill(json({ id: "rr-9", created: true, severity: "critical" }, 201));
    });
    const panel = page.getByRole("dialog");
    await panel.getByLabel("Test").selectOption("potassium");
    await panel.getByLabel("Value").fill("6.5");
    await expect(panel.getByRole("button", { name: "Save result" })).toBeEnabled();

    await panel.getByRole("button", { name: "Save result" }).click();

    await expect(page.getByText("Result recorded. It is in the review inbox.")).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(sent).toMatchObject({
      patient_id: "p-001",
      test_name: "potassium",
      value: 6.5,
      unit: "mEq/L",
      reference_low: 3.5,
      reference_high: 5.1,
    });
    expect(String(sent?.taken_at)).toMatch(/Z$/);
    await expect.poll(() => historyLoads).toBeGreaterThan(0);
  });

  test("says when the result was already recorded", async ({ page }) => {
    await open(page);
    await page.route("**/api/results/labs", (r) => r.fulfill(json({ id: "rr-9", created: false }, 201)));
    const panel = page.getByRole("dialog");
    await panel.getByLabel("Test").selectOption("potassium");
    await panel.getByLabel("Value").fill("4.1");
    await expect(panel.getByRole("button", { name: "Save result" })).toBeEnabled();

    await panel.getByRole("button", { name: "Save result" }).click();

    await expect(
      page.getByText("This result was already recorded for that draw time. Nothing was added."),
    ).toBeVisible();
  });

  test("keeps the panel open and says so when saving fails", async ({ page }) => {
    await open(page);
    await page.route("**/api/results/labs", (r) => r.fulfill({ status: 500, body: "boom" }));
    const panel = page.getByRole("dialog");
    await panel.getByLabel("Test").selectOption("potassium");
    await panel.getByLabel("Value").fill("4.1");
    await expect(panel.getByRole("button", { name: "Save result" })).toBeEnabled();

    await panel.getByRole("button", { name: "Save result" }).click();

    await expect(panel.getByRole("alert")).toContainText("could not be saved");
    await expect(panel).toBeVisible();
  });

  test("refuses a future draw date", async ({ page }) => {
    await open(page);
    const panel = page.getByRole("dialog");
    await panel.getByLabel("Test").selectOption("potassium");
    await panel.getByLabel("Value").fill("4.1");

    await panel.getByLabel("Drawn on").fill("2999-01-01T08:00");

    await expect(panel.getByText("cannot be in the future")).toBeVisible();
    await expect(panel.getByRole("button", { name: "Save result" })).toBeDisabled();
  });

  test("closes on Escape, keeps the form inside the screen and its targets tappable", async ({ page }) => {
    await open(page);
    const panel = page.getByRole("dialog");
    await panel.getByLabel("Test").selectOption("potassium");
    await panel.getByLabel("Value").fill("6.5");

    // Measure at rest: the panel scales in, and a box read mid-animation is smaller.
    await page.evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((a) => Number.isFinite(a.effect?.getComputedTiming().endTime as number))
          .map((a) => a.finished.catch(() => undefined)),
      ),
    );
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    for (const control of [
      panel.getByLabel("Test"),
      panel.getByLabel("Value"),
      panel.getByRole("button", { name: "Cancel" }),
    ]) {
      expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }

    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
});
