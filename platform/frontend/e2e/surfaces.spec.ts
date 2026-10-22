import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** Surfaces in the real browser, in both themes: a card is a hairline plus short
 * shadows, the same size as before (the hairline is a ring, not a border), and a
 * study's picture has a fine edge drawn over it. The sources are pinned in
 * lib/__tests__/surfaces.test.ts. */
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

async function open(page: import("@playwright/test").Page, theme: "light" | "dark", route = "/dashboard") {
  await seedAuth(page, "clinician");
  await mockApi(page);
  await page.addInitScript((t) => localStorage.setItem("cac_theme", t), theme);
  await page.goto(route);
  await page.waitForLoadState("networkidle");
}

for (const theme of ["light", "dark"] as const) {
  test.describe(`cards, ${theme}`, () => {
    test("have a one-pixel ring and short layers, not a diffuse cloud", async ({ page }) => {
      await open(page, theme);
      const card = page.locator(".card").first();

      const shadow = await card.evaluate((el) => getComputedStyle(el).boxShadow);

      // A ring: `0px 0px 0px 1px`, then at least two more layers.
      expect(shadow).toMatch(/0px 0px 0px 1px/);
      // Computed layers look like `rgba(...) 0px 1px 2px 0px, rgba(...) ...`.
      const layers = shadow
        .split(/,\s*(?=rgba?\()/)
        .filter((l) => !/^rgba\(0, 0, 0, 0\) 0px 0px 0px 0px$/.test(l));
      expect(layers.length).toBeGreaterThanOrEqual(3);
      // None blurs further than 40px.
      const blurs = Array.from(shadow.matchAll(/rgba?\([^)]*\)\s+(-?\d+)px\s+(-?\d+)px\s+(\d+)px/g)).map(
        (m) => Number(m[3]),
      );
      for (const blur of blurs) expect(blur).toBeLessThanOrEqual(40);
    });

    test("the surface and its shadow follow the theme", async ({ page }) => {
      await open(page, theme);
      const card = page.locator(".card").first();

      const { background, shadow } = await card.evaluate((el) => {
        const s = getComputedStyle(el);
        return { background: s.backgroundColor, shadow: s.boxShadow };
      });

      if (theme === "dark") {
        expect(background).toBe("rgb(32, 41, 57)");
        expect(shadow).toMatch(/rgba\(0, 0, 0,/);
      } else {
        expect(background).toBe("rgb(255, 255, 255)");
        expect(shadow).toMatch(/rgba\(16, 42, 83,/);
      }
    });

    test("have the card radius", async ({ page }) => {
      await open(page, theme);

      const radius = await page
        .locator(".card")
        .first()
        .evaluate((el) => getComputedStyle(el).borderTopLeftRadius);

      expect(radius).toBe("28px");
    });
  });
}

test("the controls have the control radius", async ({ page }) => {
  await page.goto("/login");
  await page.waitForLoadState("networkidle");

  const radii = await page.evaluate(() =>
    [".input", ".btn-primary"].map(
      (sel) => getComputedStyle(document.querySelector(sel)!).borderTopLeftRadius,
    ),
  );

  expect(radii).toEqual(["16px", "16px"]);
});

test.describe("pictures", () => {
  test("a study's picture has a fine edge drawn over it, and keeps its size", async ({ page }) => {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.route("**/api/medical/imaging/recent**", (r) =>
      r.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: 1,
            patient_id: "p-001",
            patient_name: "Ana Gómez",
            title: "XRAY vision description",
            date: "2026-10-01",
            image_path: "demo:xray.webp",
            preview_unavailable: null,
            model: "m",
            description: "A radiograph.",
            ai_generated: true,
          },
        ]),
      }),
    );
    await page.route("**/api/medical/imaging/preview**", (r) =>
      r.fulfill({ status: 200, contentType: "image/png", body: PNG }),
    );
    await page.goto("/imaging");
    await page.waitForLoadState("networkidle");
    const image = page.getByRole("img", { name: "XRAY vision description" });
    await expect(image).toBeVisible();

    const outline = await image.evaluate((el) => {
      const s = getComputedStyle(el);
      return { width: s.outlineWidth, style: s.outlineStyle, offset: s.outlineOffset };
    });

    expect(outline).toEqual({ width: "1px", style: "solid", offset: "-1px" });
  });
});
