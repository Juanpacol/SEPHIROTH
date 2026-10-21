import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** "Recent imaging analyses": each card shows its image, or says why it cannot.
 * The backend side (resolving `demo:<file>`, the reasons) is tested in
 * tests/test_imaging_demo.py. */
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

const ANALYSES = [
  {
    id: 1,
    patient_id: "p-001",
    patient_name: "Ana Gómez",
    title: "XRAY vision description",
    date: "2026-10-01",
    image_path: "demo:xray.webp",
    preview_unavailable: null,
    model: "gemini-flash-latest",
    description: "A frontal chest radiograph.",
    ai_generated: true,
  },
  {
    id: 2,
    patient_id: "p-002",
    patient_name: "Luis Pérez",
    title: "CT vision description",
    date: "2026-09-01",
    image_path: null,
    preview_unavailable: "file_missing",
    model: "gemini-flash-latest",
    description: "A cross-sectional CT scan.",
    ai_generated: true,
  },
];

test.describe("recent imaging analyses", () => {
  test.beforeEach(async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.route("**/api/medical/imaging/recent**", (r) =>
      r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(ANALYSES) }),
    );
    await page.route("**/api/medical/imaging/demo", (r) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            image: "demo:xray.webp",
            modality: "XRAY",
            region: "Chest",
            description: "A frontal chest radiograph showing the thoracic cage.",
            model: "gemini-flash-latest",
          },
        ]),
      }),
    );
    await page.route("**/api/medical/imaging/preview**", (r) =>
      r.fulfill({ status: 200, contentType: "image/png", body: PNG }),
    );
    await page.goto("/imaging");
    await page.waitForLoadState("networkidle");
  });

  test("the sample panel shows a real study and its analysis, not a broken image", async ({ page }) => {
    const sample = page.getByTestId("imaging-sample");

    await expect(sample).toContainText("A frontal chest radiograph");
    const image = sample.getByRole("img", { name: "XRAY Chest" });
    await expect(image).toBeVisible();
    expect(await image.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
    await expect(page.locator('img[src="/landing/imaging-vision.jpg"]')).toHaveCount(0);
  });

  test("a card with an image shows it, from the demo path", async ({ page }) => {
    const card = page.locator(".card", { hasText: "XRAY vision description" });

    const image = card.getByRole("img", { name: "XRAY vision description" });
    await expect(image).toBeVisible();
    expect(await image.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
    await expect(card.getByTestId("preview-unavailable")).toHaveCount(0);
    await expect(card.getByRole("button", { name: "Reopen for Vision AI" })).toBeEnabled();
  });

  test("a card without one says why, instead of a bare 'No preview'", async ({ page }) => {
    const card = page.locator(".card", { hasText: "CT vision description" });

    await expect(card.getByTestId("preview-unavailable")).toContainText("Image not available");
    await expect(card.getByTestId("preview-unavailable")).toContainText("not on this server");
    await expect(page.getByText("No preview", { exact: true })).toHaveCount(0);
    await expect(card.getByRole("button", { name: "Reopen for Vision AI" })).toBeDisabled();
  });

  test("both kinds of card are the same size, so nothing jumps when an image loads", async ({ page }) => {
    const boxes = await Promise.all(
      ["XRAY vision description", "CT vision description"].map((title) =>
        page.locator(".card", { hasText: title }).locator(".aspect-square").boundingBox(),
      ),
    );

    expect(Math.abs(boxes[0]!.height - boxes[1]!.height)).toBeLessThanOrEqual(1);
    expect(Math.abs(boxes[0]!.width - boxes[1]!.width)).toBeLessThanOrEqual(1);
  });

  test("the cards stay inside the screen", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    for (const button of [
      ...(await page.getByRole("button", { name: "View full analysis" }).all()),
      ...(await page.getByRole("button", { name: "Reopen for Vision AI" }).all()),
    ]) {
      expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  });
});
