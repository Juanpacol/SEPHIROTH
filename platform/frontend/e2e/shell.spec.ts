import { expect, test } from "@playwright/test";
import { seedAuth } from "./fixtures/auth";
import { mockApi } from "./fixtures/mock-api";

/** The navigation shell itself: exactly one of the two navigations is present
 * at any width, and the mobile drawer behaves like a modal. */

test.beforeEach(async ({ page }) => {
  await seedAuth(page, "clinician");
  await mockApi(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("main")).toBeVisible();
});

const tabBar = (page: import("@playwright/test").Page) => page.getByRole("navigation", { name: /primary|principal/i });
const menuButton = (page: import("@playwright/test").Page) => page.getByRole("button", { name: /^(menu|menú)$/i });

/** Keyed on the actual width, not the project name: the breakpoint is `md`
 * (768px), so any new narrow project belongs on the mobile side automatically. */
const isPhoneWidth = (testInfo: import("@playwright/test").TestInfo): boolean =>
  (testInfo.project.use.viewport?.width ?? 0) < 768;

test("exactly one navigation is visible for the viewport", async ({ page }, testInfo) => {
  const phone = isPhoneWidth(testInfo);
  const sidebar = page.locator("aside");

  if (phone) {
    await expect(tabBar(page)).toBeVisible();
    await expect(menuButton(page)).toBeVisible();
    await expect(sidebar).toBeHidden();
  } else {
    await expect(sidebar).toBeVisible();
    await expect(tabBar(page)).toBeHidden();
    await expect(menuButton(page)).toBeHidden();
  }
});

test("the drawer opens, traps focus, and closes on Escape", async ({ page }, testInfo) => {
  test.skip(!isPhoneWidth(testInfo), "The drawer only exists below md.");

  await menuButton(page).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer).toBeVisible();

  // Focus must be inside the drawer, or Tab walks straight into the page behind
  // it and a screen reader never learns anything opened.
  await expect
    .poll(() => drawer.evaluate((el) => el.contains(document.activeElement)))
    .toBe(true);

  // Reachable only from the drawer — it is not a primary tab.
  await expect(drawer.getByRole("link", { name: /evidence|evidencia/i })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("page content is readable under the tab bar at the end of the page", async ({ page }, testInfo) => {
  test.skip(!isPhoneWidth(testInfo), "The tab bar only exists below md.");

  // The footer disclaimer is the last thing in the flow and the first casualty
  // of a floating bar. Scrolled to the end, it has to be fully clear of it.
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const footer = document.querySelector("footer")!.getBoundingClientRect().bottom;
        const bar = document
          .querySelector("nav[aria-label]")!
          .closest("div")!
          .getBoundingClientRect().top;
        return Math.round(footer - bar);
      }),
    )
    // 1px of slack for subpixel rounding, same tolerance the overflow test uses.
    .toBeLessThanOrEqual(1);
});

test("the copilot button clears the tab bar", async ({ page }, testInfo) => {
  test.skip(!isPhoneWidth(testInfo), "They only share an edge on a phone.");

  const fab = page.getByRole("button", { name: /copilot|copiloto/i }).first();
  const fabBox = await fab.boundingBox();
  const barBox = await tabBar(page).boundingBox();

  expect(fabBox, "copilot button has no box").not.toBeNull();
  expect(barBox, "tab bar has no box").not.toBeNull();
  expect(fabBox!.y + fabBox!.height, "the copilot button overlaps the tab bar").toBeLessThanOrEqual(barBox!.y);
});

test("the copilot panel fills the screen on a phone", async ({ page }, testInfo) => {
  test.skip(!isPhoneWidth(testInfo), "It is a floating panel from md: up.");

  await page.getByRole("button", { name: /copilot|copiloto/i }).first().click();
  const panel = page.getByRole("dialog");
  await expect(panel).toBeVisible();

  const box = await panel.boundingBox();
  const viewport = page.viewportSize()!;
  // A 420px floating card inside a 390px viewport is not a card. Full-bleed, and
  // over the tab bar rather than beside it.
  expect(box!.width, "the copilot panel is narrower than the screen").toBeGreaterThanOrEqual(
    viewport.width - 1,
  );
  expect(box!.height).toBeGreaterThanOrEqual(viewport.height - 1);
});

test("cancelling an appointment goes through the in-app dialog", async ({ page }, testInfo) => {
  // A native `window.confirm` would block the page and never resolve here, so a
  // timeout on this test is the signal that one has come back.
  await page.goto("/schedule");
  await expect(page.getByRole("main")).toBeVisible();
  await page.waitForLoadState("networkidle");

  // The two views offer the action differently and both have to reach the same
  // dialog: the week grid makes the whole appointment block the button, the day
  // agenda gives the row an explicit labelled one.
  const trigger = isPhoneWidth(testInfo)
    ? page.getByRole("button", { name: /cancel appointment|cancelar cita/i }).first()
    : page.getByRole("button", { name: /Restrepo/i }).first();
  await trigger.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(/Restrepo/);

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});
