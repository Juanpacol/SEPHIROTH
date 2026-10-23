import { expect, test, type Page } from "@playwright/test";

/** The landing page is one dark page, and the FAQ opens and closes, in a real browser at every viewport.
 * Copy and data are pinned in lib/__tests__/marketing-agents.test.ts. */
const rgb = (css: string) =>
  (css.match(/\d+(\.\d+)?/g) ?? []).slice(0, 3).map(Number) as [number, number, number];
const lum = ([r, g, b]: [number, number, number]) => {
  const f = (v: number) => (v / 255 <= 0.03928 ? v / 255 / 12.92 : ((v / 255 + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const contrast = (a: [number, number, number], b: [number, number, number]) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

async function settle(page: Page, selector: string) {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.locator(selector).scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
}

test.describe("a dark landing, whatever theme the reader chose", () => {
  // The app's own theme is stored in localStorage; the landing must ignore a stored "light".
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("cac_theme", "light"));
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("is dark although the stored theme is light", async ({ page }) => {
    await expect(page.locator("html")).toHaveClass(/dark/);
    const background = await page
      .locator("main")
      .evaluate((el) => getComputedStyle(el.parentElement as HTMLElement).backgroundColor);
    expect(background).toBe("rgb(18, 27, 44)");
  });

  for (const selector of ["#features", "#how-it-works", "#safeguards", "#agents", "#faq"]) {
    test(`${selector} has no light section: its text clears AA on the page's navy`, async ({ page }) => {
      const section = page.locator(selector);
      await section.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);

      const { text, heading } = await section.evaluate((el) => {
        const h = el.querySelector("h1, h2, h3") as HTMLElement;
        return { text: getComputedStyle(el).color, heading: getComputedStyle(h).color };
      });

      const navy = rgb("rgb(18, 27, 44)");
      expect(contrast(rgb(text), navy)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(rgb(heading), navy)).toBeGreaterThanOrEqual(4.5);
    });
  }

  test("has no theme buttons, and still lets the reader switch language", async ({ page }) => {
    await expect(page.getByRole("button", { name: "Light" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Dark" })).toHaveCount(0);
    // The switch is in the header from md up, and in the menu sheet on a phone.
    if (page.viewportSize()!.width < 768) await page.getByRole("button", { name: "Menu" }).click();
    await expect(page.getByRole("button", { name: "Toggle language" }).first()).toBeVisible();
  });

  test("gives the reader's theme back when they leave for the app", async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("html")).not.toHaveClass(/dark/);
  });
});

test.describe("FAQ", () => {
  test("opens and closes from the keyboard, and says its state", async ({ page, hasTouch }) => {
    test.skip(hasTouch, "no keyboard");
    await settle(page, "#faq");
    const first = page.locator("#faq details").first();
    const summary = first.locator("summary");

    await summary.focus();
    await page.keyboard.press("Enter");
    await expect(first).toHaveAttribute("open", "");
    await page.keyboard.press("Space");
    await expect(first).not.toHaveAttribute("open", "");
    await expect(summary).toBeFocused();
  });

  test("opening an answer does not move anything above it", async ({ page }) => {
    await settle(page, "#faq");
    const top = () =>
      page.locator("#faq h2").evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
    const before = await top();

    await page.locator("#faq details summary").nth(2).click();
    await page.waitForTimeout(400);

    expect(Math.abs((await top()) - before)).toBeLessThanOrEqual(1);
  });
});
