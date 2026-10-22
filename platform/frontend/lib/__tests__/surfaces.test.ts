import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import config from "../../tailwind.config";

/** Surfaces (AB#41): one hairline, short layered shadows and nested radii, the same in
 * light and dark. Read as text so a diffuse shadow or a one-off radius fails here. */
const root = path.join(__dirname, "../..");
const read = (rel: string) => readFileSync(path.join(root, rel), "utf8");
const css = read("app/globals.css");
const extend = config.theme?.extend as Record<string, Record<string, string>>;

function sources(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(path.join(root, dir))) {
    const rel = path.join(dir, name);
    if (name === "node_modules" || name === ".next" || name === "__tests__") continue;
    if (statSync(path.join(root, rel)).isDirectory()) sources(rel, out);
    else if (/\.tsx$/.test(name)) out.push(rel);
  }
  return out;
}

describe("shadows", () => {
  const surfaces = ["raised", "raised-lg", "popover"] as const;

  it.each(surfaces)("%s starts with the hairline, then short layers", (name) => {
    const value = extend.boxShadow[name];
    expect(value.startsWith("0 0 0 1px rgb(var(--color-line)")).toBe(true);
    expect(value.split("), ").length).toBeGreaterThanOrEqual(3);
  });

  /** Each layer as [x, y, blur, spread] in px. */
  function layers(value: string): number[][] {
    return value.split(/\),\s*/).map((layer) =>
      layer
        .replace(/rgb\(.*$/, "")
        .trim()
        .split(/\s+/)
        .map((n) => parseFloat(n) || 0),
    );
  }

  it.each(surfaces)("%s is tight: no layer blurs further than 40px", (name) => {
    for (const [, , blur] of layers(extend.boxShadow[name])) expect(blur).toBeLessThanOrEqual(40);
  });

  it.each(["raised-lg", "popover"] as const)("%s pulls its long layer in with a negative spread", (name) => {
    const [, , blur, spread] = layers(extend.boxShadow[name]).at(-1)!;
    expect(blur).toBeGreaterThanOrEqual(24);
    expect(spread).toBeLessThan(0);
  });

  it("never shares a name with a colour: Tailwind would make `shadow-<colour>` and the colour's rule would win", () => {
    const colours = Object.keys((extend as unknown as { colors: Record<string, unknown> }).colors ?? {});
    for (const name of Object.keys(extend.boxShadow)) expect(colours, name).not.toContain(name);
  });

  it("casts them in a colour that changes with the theme: blue on light, black on navy", () => {
    expect(css).toMatch(/:root\s*\{[^}]*--shadow-ink: 16 42 83;/);
    expect(css).toMatch(/\.dark\s*\{[^}]*--shadow-ink: 0 0 0;/);
    expect(css).toMatch(/\.dark\s*\{[^}]*--shadow-strength: 3\.5;/);
    for (const value of Object.values(extend.boxShadow)) expect(value).not.toMatch(/rgba\(16, 42, 83/);
  });

  it("nothing in the app uses an untokened shadow", () => {
    const offenders = sources("app")
      .concat(sources("components"))
      .filter((f) => /\bshadow-(sm|md|lg|xl|2xl)\b/.test(read(f)));
    expect(offenders).toEqual([]);
    expect(css).not.toMatch(/@apply[^;]*\bshadow-(sm|md|lg|xl|2xl)\b/);
  });
});

describe("radii", () => {
  const radii = extend.borderRadius;
  const px = (v: string) => parseFloat(v) * 16;

  it("has a surface, a control and an inner radius, each smaller than the one around it", () => {
    expect(px(radii.card)).toBeGreaterThan(px(radii.control));
    expect(px(radii.control)).toBeGreaterThan(px(radii.inner));
  });

  it("an inner corner is the card's radius minus the padding between them, not smaller than that", () => {
    const cardPadding = 20; // `.card` is p-5
    expect(px(radii.inner)).toBeGreaterThanOrEqual(px(radii.card) - cardPadding - 12);
  });

  it("the shared surfaces use them", () => {
    expect(css).toMatch(/\.card\s*\{\s*@apply bg-card rounded-card shadow-raised/);
    expect(css).toMatch(/\.btn\s*\{[^}]*rounded-control/);
    expect(css).toMatch(/\.input\s*\{\s*@apply w-full rounded-control/);
  });
});

describe("pictures", () => {
  it("have a fine edge drawn over them, as an outline so they keep their size", () => {
    const rule = css.match(/\.media-edge\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toContain("outline: 1px solid rgb(var(--color-ink)");
    expect(rule).toContain("outline-offset: -1px");
  });

  it("the study previews and the upload preview use it", () => {
    expect(read("app/imaging/page.tsx")).toMatch(/media-edge[^"]*object-cover/);
    expect(read("components/image-dropzone.tsx")).toContain("media-edge");
  });
});
