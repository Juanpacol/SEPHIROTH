import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** Interaction rules in the real browser, at every viewport: keyboard focus is
 * visible, hover effects exist only where hovering does, and panels leave with a
 * short animation (or none, when motion is reduced). The CSS rules themselves are
 * pinned in lib/__tests__/interactions.test.ts. */
test.describe("focus", () => {
  test("a button reached with the keyboard has a visible ring", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "touch devices have no keyboard focus ring");
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    const submit = page.getByRole("button", { name: "Sign in" });
    await submit.focus();
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("Tab");

    await expect(submit).toBeFocused();
    // `.btn` transitions every property, the outline included, so read it once it settles.
    await expect
      .poll(() =>
        submit.evaluate((el) => {
          const s = getComputedStyle(el);
          return { width: s.outlineWidth, style: s.outlineStyle, offset: s.outlineOffset };
        }),
      )
      .toEqual({ width: "2px", style: "solid", offset: "2px" });
  });

  test("a mouse click does not draw the ring", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "no mouse");
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    const submit = page.getByRole("button", { name: "Sign in" });

    await submit.click();

    const width = await submit.evaluate((el) => getComputedStyle(el).outlineStyle);
    expect(width).toBe("none");
  });
});

test.describe("hover", () => {
  test("the button arc shows on hover where the device can hover, and never on touch", async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    const canHover = await page.evaluate(() => window.matchMedia("(hover: hover)").matches);
    const submit = page.getByRole("button", { name: "Sign in" });
    const arc = () => submit.evaluate((el) => getComputedStyle(el, "::after").opacity);

    expect(await arc()).toBe("0");
    if (canHover) {
      await submit.hover();
      await expect.poll(arc).toBe("1");
    } else {
      await submit.tap();
      expect(await arc()).toBe("0");
    }
  });

  test("the arc adds no size: the button is the same box with or without it", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "needs a pointer");
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    const submit = page.getByRole("button", { name: "Sign in" });
    const before = await submit.boundingBox();

    await submit.hover();
    await page.waitForTimeout(1000);
    const after = await submit.boundingBox();

    expect(after!.width).toBeCloseTo(before!.width, 0);
    expect(after!.height).toBeCloseTo(before!.height, 0);
  });
});

test.describe("panels", () => {
  async function openPanel(page: import("@playwright/test").Page) {
    await seedAuth(page, "clinician");
    await mockApi(page);
    await page.goto("/patients/p-001");
    await page.waitForLoadState("networkidle");
    await page.getByRole("button", { name: "Record result" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  }

  test("a panel fades out before it goes", async ({ page }) => {
    await openPanel(page);

    await page.keyboard.press("Escape");

    // Still there, leaving and unclickable, then gone.
    const state = await page.evaluate(
      () => document.querySelector('[role="dialog"]')?.getAttribute("data-state") ?? null,
    );
    expect(["closed", null]).toContain(state);
    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 1500 });
  });

  test("with reduced motion a panel goes at once", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openPanel(page);

    await page.keyboard.press("Escape");

    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 150 });
  });

  test("closing a panel hands the focus back to the button that opened it", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "a tap does not focus a button in Safari, so there is nothing to give back");
    await openPanel(page);

    await page.keyboard.press("Escape");

    await expect(page.getByRole("button", { name: "Record result" })).toBeFocused();
  });
});
