import { expect, test } from "@playwright/test";

/** Nothing on the landing page may move on its own. Things that did: an image section that
 * reserved a guessed height and grew to its real one (sliding the page down behind a height
 * transition), and a walkthrough that resized with each stage while autoplay ran. Both pushed
 * every section below them around, which looked like the page scrolling by itself. */
test.describe("landing: the page holds still", () => {
  /** Where a section sits on the page, sampled for a few seconds after load. */
  async function sample(page: import("@playwright/test").Page, headings: string[], ms: number) {
    const seen: Record<string, number[]> = Object.fromEntries(headings.map((h) => [h, []]));
    const end = Date.now() + ms;
    while (Date.now() < end) {
      const tops = await page.evaluate((names) => {
        const out: Record<string, number> = {};
        for (const name of names) {
          const el = Array.from(document.querySelectorAll("h1,h2")).find((h) =>
            h.textContent?.includes(name),
          );
          if (el) out[name] = Math.round(el.getBoundingClientRect().top + window.scrollY);
        }
        return out;
      }, headings);
      for (const [name, top] of Object.entries(tops)) seen[name].push(top);
      await page.waitForTimeout(200);
    }
    return seen;
  }

  test("the sections below the hero stay where they are while autoplay runs", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    // Past hydration and the entrance animations, then long enough for the
    // walkthrough to move through three of its stages.
    await page.waitForTimeout(1500);

    const headings = ["Features", "The same workup", "How we keep it fro"];
    const seen = await sample(page, headings, 7000);

    for (const name of headings) {
      const tops = seen[name];
      expect(tops.length, name).toBeGreaterThan(10);
      expect(
        Math.max(...tops) - Math.min(...tops),
        `${name} moved: ${Array.from(new Set(tops)).join(" -> ")}`,
      ).toBeLessThanOrEqual(1);
    }
  });

  test("the page does not scroll by itself", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    const ys: number[] = [];
    for (let i = 0; i < 20; i++) {
      ys.push(await page.evaluate(() => Math.round(window.scrollY)));
      await page.waitForTimeout(250);
    }

    expect(new Set(ys)).toEqual(new Set([0]));
  });
});
