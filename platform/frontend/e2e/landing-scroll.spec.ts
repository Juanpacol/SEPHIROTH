import { expect, test, type Page } from "@playwright/test";

/** The landing's scroll-linked motion in a real browser: the footer that comes up as you
 * reach it, the hero that drifts away, and the feature panel that follows the list. The
 * maths is pinned in lib/__tests__/scroll-effects.test.ts. */
const cssVar = (page: Page, name: string) =>
  page.evaluate((n) => document.documentElement.style.getPropertyValue(n).trim(), name);

async function toEnd(page: Page) {
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
}

test.describe("footer", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("is faded and low until the reader reaches it, then fully there", async ({ page }) => {
    const content = page.locator("[data-footer-content]");
    await page.waitForTimeout(500);
    expect(Number(await cssVar(page, "--footer-progress"))).toBeLessThan(0.05);
    expect(Number(await content.evaluate((el) => getComputedStyle(el).opacity))).toBeLessThan(0.5);

    await toEnd(page);

    await expect.poll(async () => Number(await cssVar(page, "--footer-progress"))).toBeGreaterThan(0.98);
    await expect
      .poll(async () => Number(await content.evaluate((el) => getComputedStyle(el).opacity)))
      .toBeGreaterThan(0.98);
    expect(parseFloat(await cssVar(page, "--footer-lift"))).toBeLessThan(2);
  });

  test("follows the scroll with a lag, not in one jump", async ({ page }) => {
    await page.waitForTimeout(500);
    await toEnd(page);

    const seen = new Set<string>();
    for (let i = 0; i < 6; i++) {
      seen.add(await cssVar(page, "--footer-progress"));
      await page.waitForTimeout(40);
    }

    expect(seen.size).toBeGreaterThan(2);
  });

  test("stays in the page's flow: its links are reachable and in order", async ({ page }) => {
    await toEnd(page);
    await page.waitForTimeout(1500);

    const footer = page.locator("footer[data-footer-reveal]");
    const link = footer.getByRole("link", { name: "Repository" });
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "https://github.com/Juanpacol/SEPHIROTH");
    const box = (await link.boundingBox())!;
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  });

  test("the wordmark behind it is decoration only", async ({ page }) => {
    const mark = page.locator("[data-footer-wordmark]");

    await expect(mark).toHaveText("SEPHIROTH");
    await expect(mark.locator("xpath=ancestor::div[@aria-hidden='true']")).toHaveCount(1);
  });

  test("the footer's columns are the header's menus", async ({ page }) => {
    await toEnd(page);
    await page.waitForTimeout(1200);

    const footer = page.locator("footer[data-footer-reveal]");
    for (const group of ["Product", "For patients", "Open source"]) {
      await expect(footer.getByRole("navigation", { name: group })).toBeVisible();
    }
  });
});

test.describe("hero", () => {
  test("drifts and fades as you scroll away, and is untouched at the top", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const content = page.locator("[data-hero-content]");
    await page.waitForTimeout(600);
    expect(Number(await content.evaluate((el) => getComputedStyle(el).opacity))).toBeGreaterThan(0.99);

    await page.evaluate(() => window.scrollTo(0, 500));

    await expect.poll(async () => parseFloat(await cssVar(page, "--hero-shift"))).toBeGreaterThan(100);
    await expect
      .poll(async () => Number(await content.evaluate((el) => getComputedStyle(el).opacity)))
      .toBeLessThan(0.95);
  });

  test("moving the hero never moves the page: it is only a transform", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const next = page.locator("#analysis-demo, #features").first();
    const top = () => next.evaluate((el) => Math.round(el.getBoundingClientRect().top + window.scrollY));
    const before = await top();

    await page.evaluate(() => window.scrollTo(0, 600));
    await page.waitForTimeout(800);

    expect(Math.abs((await top()) - before)).toBeLessThanOrEqual(1);
  });
});

test.describe("reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("nothing travels: the footer is simply there and the hero stays put", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    expect(await cssVar(page, "--footer-progress")).toBe("1");
    expect(await cssVar(page, "--hero-shift")).toBe("0px");
    await page.evaluate(() => window.scrollTo(0, 600));
    await page.waitForTimeout(400);
    expect(await cssVar(page, "--hero-shift")).toBe("0px");
    expect(
      Number(await page.locator("[data-hero-content]").evaluate((el) => getComputedStyle(el).opacity)),
    ).toBeGreaterThan(0.99);
  });
});

test.describe("features", () => {
  test("have a numbered entry each, in the order the reader meets them", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const eyebrows = await page.locator("#features article .border-l-2 .eyebrow").allInnerTexts();

    expect(eyebrows.map((t) => t.replace(/\s+/g, " "))).toEqual([
      "01 · ASK",
      "02 · CITE",
      "03 · VERIFY",
      "04 · SEE",
      "05 · FOLLOW UP",
      "06 · SHARE",
    ]);
  });

  test("on a wide screen the panel stays in view and follows the list", async ({ page }) => {
    test.skip(page.viewportSize()!.width < 1024, "the sticky panel is for lg and up");
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const panel = page.getByTestId("feature-panel");

    await page.locator("#feature-see").scrollIntoViewIfNeeded();
    await page.locator("#feature-see").evaluate((el) => el.scrollIntoView({ block: "center" }));
    await page.waitForTimeout(900);

    await expect(page.locator("[data-layer='see']")).toHaveAttribute("aria-hidden", "false");
    await expect(page.locator("[data-layer='ask']")).toHaveAttribute("aria-hidden", "true");
    const box = (await panel.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize()!.height);
  });

  test("on a phone each feature carries its own media and there is no sticky panel", async ({ page }) => {
    test.skip(page.viewportSize()!.width >= 1024, "that is the wide layout");
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("feature-panel")).toBeHidden();
    const first = page.locator("#feature-ask .aspect-\\[4\\/3\\]");
    await first.scrollIntoViewIfNeeded();
    await expect(first).toBeVisible();
  });

  test("the page does not overflow sideways with all of this on it", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
