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
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
  });

  test("six cells, numbered, in the order the reader meets them", async ({ page }) => {
    const labels = await page.locator("#features article .eyebrow").allInnerTexts();

    expect(labels.map((t) => t.replace(/\s+/g, " "))).toEqual([
      "#1 ASK",
      "#2 CITE",
      "#3 VERIFY",
      "#4 SEE",
      "#5 FOLLOW UP",
      "#6 SHARE",
    ]);
  });

  test("the title is in the display face and the section is a navy band", async ({ page }) => {
    const heading = page.locator("#features h2");

    expect(await heading.evaluate((el) => getComputedStyle(el).fontFamily)).toMatch(/antonio/i);
    expect(await page.locator("#features").evaluate((el) => getComputedStyle(el).backgroundColor)).toBe(
      "rgb(18, 27, 44)",
    );
  });

  test("three columns on a wide screen, two on a tablet, one on a phone", async ({ page }) => {
    const width = page.viewportSize()!.width;
    const tops = await page
      .locator("#features article")
      .evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().top + window.scrollY)));
    const perRow = tops.filter((t) => Math.abs(t - tops[0]) <= 2).length;

    expect(perRow).toBe(width >= 1024 ? 3 : width >= 768 ? 2 : 1);
  });

  test("each cell's picture is square, and every cell is the same size as its neighbours", async ({
    page,
  }) => {
    const frames = await page
      .locator("#features [data-parallax-frame]")
      .evaluateAll((els) =>
        els.map((el) => ({ w: el.getBoundingClientRect().width, h: el.getBoundingClientRect().height })),
      );

    expect(frames).toHaveLength(6);
    for (const { w, h } of frames) expect(Math.abs(w - h)).toBeLessThanOrEqual(1);
    expect(Math.abs(frames[0].w - frames[1].w)).toBeLessThanOrEqual(1);
  });

  test("a picture drifts inside its frame as you scroll, and never leaves a gap", async ({ page }) => {
    test.skip(page.viewportSize()!.width < 768, "the picture with a drift is the X-ray in the fourth cell");
    const img = page.locator("#feature-see img[data-parallax]");
    await img.scrollIntoViewIfNeeded();
    await page.waitForTimeout(900);

    const shift = async () =>
      parseFloat(await img.evaluate((el) => getComputedStyle(el).getPropertyValue("--py-img") || "0"));
    const first = await shift();
    await page.evaluate(() => window.scrollBy(0, 220));
    await page.waitForTimeout(900);
    const second = await shift();

    expect(second).not.toBe(first);
    const { frame, picture } = await img.evaluate((el) => ({
      frame: el.closest("[data-parallax-frame]")!.getBoundingClientRect(),
      picture: el.getBoundingClientRect(),
    }));
    expect(picture.top).toBeLessThanOrEqual(frame.top + 0.5);
    expect(picture.bottom).toBeGreaterThanOrEqual(frame.bottom - 0.5);
  });

  test("the page does not overflow sideways with all of this on it", async ({ page }) => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
