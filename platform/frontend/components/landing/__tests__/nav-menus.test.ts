import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { NAV_MENUS, NAV_SECTIONS } from "@/components/landing/nav-menus";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";

/** The header may only point at places that exist, and say what is there. */
const root = path.join(__dirname, "../../..");
const page = readFileSync(path.join(root, "app/(marketing)/page.tsx"), "utf8");
const items = NAV_MENUS.flatMap((m) => [...(m.promo ? [m.promo] : []), ...m.items]);

describe("landing header menus", () => {
  it("has a menu that leaves the page, not only jumps within it", () => {
    const leaves = NAV_MENUS.filter((m) => m.items.some((i) => !i.href.startsWith("#")));
    expect(leaves.length).toBeGreaterThanOrEqual(2);
  });

  it("every in-page jump lands on a section that exists", () => {
    for (const item of items.filter((i) => i.href.startsWith("#"))) {
      expect(page, item.href).toContain(`id="${item.href.slice(1)}"`);
    }
  });

  it("every internal route is a page of the app", () => {
    for (const item of items.filter((i) => i.href.startsWith("/"))) {
      expect(existsSync(path.join(root, "app", item.href, "page.tsx")), item.href).toBe(true);
    }
  });

  it("every outside link goes to the project's own repository and is marked external", () => {
    const outside = items.filter((i) => /^https?:/.test(i.href));
    expect(outside.length).toBeGreaterThan(0);
    for (const item of outside) {
      expect(item.href, item.href).toMatch(/^https:\/\/github\.com\/Juanpacol\/SEPHIROTH(\/|$)/);
      expect(item.external, item.href).toBe(true);
    }
    for (const item of items.filter((i) => !/^https?:/.test(i.href))) expect(item.external).toBeFalsy();
  });

  it("every item has a title and a line about what is behind it, in both languages", () => {
    const keys = [
      ...NAV_MENUS.flatMap((m) => [m.labelKey, m.eyebrowKey]),
      ...items.flatMap((i) => [i.titleKey, i.bodyKey]),
      "marketing.nav.external",
    ];
    for (const key of keys) {
      expect((EN as Record<string, string>)[key], `en ${key}`).toBeTruthy();
      expect((ES as Record<string, string>)[key], `es ${key}`).toBeTruthy();
    }
  });

  it("the scroll-spy watches exactly the sections the items point at", () => {
    const targets = items.filter((i) => i.href.startsWith("#")).map((i) => i.href.slice(1));
    expect([...NAV_SECTIONS].sort()).toEqual([...targets].sort());
  });
});
