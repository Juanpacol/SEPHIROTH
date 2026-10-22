import { expect, test, type Page } from "@playwright/test";

/** The landing's navy bands and FAQ, in a real browser at every viewport.
 * Copy and data are pinned in lib/__tests__/{bands,marketing-agents}.test.ts. */
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

test.describe("navy bands on the white page", () => {
  for (const [name, selector] of [
    ["hero", "section.band-dark >> nth=0"],
    ["safeguards", "#safeguards"],
    ["closing", "section.band-dark >> nth=-1"],
  ] as const) {
    test(`the ${name} band is navy and its text clears AA`, async ({ page }) => {
      await page.goto("/");
      await page.waitForLoadState("networkidle");
      const band = page.locator(selector);
      await band.scrollIntoViewIfNeeded();
      await page.waitForTimeout(600);

      const { background, text, heading } = await band.evaluate((el) => {
        const h = el.querySelector("h1, h2, h3") as HTMLElement;
        return {
          background: getComputedStyle(el).backgroundColor,
          text: getComputedStyle(el).color,
          heading: getComputedStyle(h).color,
        };
      });

      expect(background).toBe("rgb(18, 27, 44)");
      expect(contrast(rgb(text), rgb(background))).toBeGreaterThanOrEqual(4.5);
      expect(contrast(rgb(heading), rgb(background))).toBeGreaterThanOrEqual(4.5);
    });
  }

  test("the page alternates: white sections sit between the navy ones", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const tones = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main > section, body > div section"))
        .filter((s) => (s as HTMLElement).offsetHeight > 200)
        .map((s) => (s.classList.contains("band-dark") ? "navy" : "light")),
    );

    expect(tones.filter((t) => t === "navy").length).toBeGreaterThanOrEqual(2);
    expect(tones.join(" ")).toMatch(/navy light/);
    expect(tones.join(" ")).toMatch(/light navy/);
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
