import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import config from "../../tailwind.config";

/** The design tokens in app/globals.css: the dark theme is the brand blue mixed
 * with black, every text/background pair clears WCAG AA, and the motion tokens
 * exist. Reads the CSS as text, so a value edited by hand and out of step with the
 * recipe fails here. See docs/04-development/design-tokens.md. */
const css = readFileSync(path.join(__dirname, "../../app/globals.css"), "utf8");

type RGB = [number, number, number];

function block(selector: string): Record<string, RGB | string> {
  const body = css.match(new RegExp(`(?:^|\\n)${selector.replace(".", "\\.")}\\s*\\{([^}]*)\\}`))?.[1] ?? "";
  const out: Record<string, RGB | string> = {};
  for (const [, name, value] of Array.from(body.matchAll(/--([\w-]+):\s*([^;]+);/g))) {
    const triple = value.trim().match(/^(\d+) (\d+) (\d+)$/);
    out[name] = triple ? [Number(triple[1]), Number(triple[2]), Number(triple[3])] : value.trim();
  }
  return out;
}

const light = block(":root");
const dark = block(".dark");

const BRAND: RGB = [54, 131, 248]; // #3683F8
const BLACK: RGB = [0, 0, 0];
const WHITE: RGB = [255, 255, 255];
/** sRGB mix, `a` weighted `weight` (0..1), rounded like the browser would. */
const mix = (a: RGB, b: RGB, weight: number): RGB =>
  a.map((v, i) => Math.round(v * weight + b[i] * (1 - weight))) as RGB;

function luminance([r, g, b]: RGB): number {
  const f = (v: number) => (v / 255 <= 0.03928 ? v / 255 / 12.92 : ((v / 255 + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function contrast(a: RGB, b: RGB): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
const near = (a: RGB, b: RGB) => a.every((v, i) => Math.abs(v - b[i]) <= 1);
const rgb = (theme: typeof light, name: string) => theme[name] as RGB;

describe("light theme", () => {
  it("is exactly what it was before the tokens: the redesign does not touch it", () => {
    expect(light).toMatchObject({
      "color-ink": [6, 6, 6],
      "color-surface": [235, 243, 254],
      "color-card": [255, 255, 255],
      "color-line": [216, 216, 216],
      "color-muted": [138, 148, 166],
      "color-primary-soft": [234, 242, 254],
    });
  });
});

describe("dark theme", () => {
  const surface = mix(WHITE, mix(BRAND, BLACK, 0.14), 0.04);

  it("is derived from the brand blue, not hand-picked greys", () => {
    expect(near(rgb(dark, "color-surface"), surface)).toBe(true);
    expect(near(rgb(dark, "color-card"), mix(WHITE, surface, 0.06))).toBe(true);
    expect(near(rgb(dark, "color-line"), mix(WHITE, surface, 0.14))).toBe(true);
    expect(near(rgb(dark, "color-primary-soft"), mix(BRAND, surface, 0.18))).toBe(true);
  });

  it("has a blue cast: every surface leans blue, none is a neutral grey", () => {
    for (const name of ["color-surface", "color-card", "color-line"]) {
      const [r, g, b] = rgb(dark, name);
      expect(b - r, name).toBeGreaterThanOrEqual(20);
      expect(b, name).toBeGreaterThan(g);
    }
  });

  it("no longer carries the neutral iOS greys", () => {
    const values = Object.values(dark).map((v) => (Array.isArray(v) ? v.join(" ") : v));
    for (const old of ["8 8 10", "28 28 30", "56 56 60", "245 245 247", "24 38 66"]) {
      expect(values).not.toContain(old);
    }
    expect(css).not.toMatch(/iOS "Dark Mode" palette/);
  });
});

describe("contrast (WCAG AA, 4.5:1 for text)", () => {
  const pairs: [string, string][] = [
    ["color-ink", "color-surface"],
    ["color-ink", "color-card"],
    ["color-muted", "color-surface"],
    ["color-muted", "color-card"],
    ["color-primary-ink", "color-surface"],
    ["color-primary-ink", "color-card"],
    ["color-primary-ink", "color-primary-soft"],
  ];

  for (const [name, theme] of [
    ["dark", dark],
    ["light", light],
  ] as const) {
    for (const [fg, bg] of pairs) {
      // Known gap, recorded rather than hidden: the light `muted` grey is 3.1:1 on
      // white. It is not changed here because the light theme must not move.
      const knownLightGap = name === "light" && fg === "color-muted";
      it(`${name}: ${fg} on ${bg}${knownLightGap ? " (known gap, below AA)" : ""}`, () => {
        const ratio = contrast(rgb(theme as typeof light, fg), rgb(theme as typeof light, bg));
        if (knownLightGap) expect(ratio).toBeLessThan(4.5);
        else expect(ratio).toBeGreaterThanOrEqual(4.5);
      });
    }
  }

  it("white text on the primary button fill clears AA (it was 3.65:1 on the brand blue)", () => {
    expect(contrast(WHITE, BRAND)).toBeLessThan(4.5);
    expect(contrast(WHITE, rgb(light, "color-primary-fill"))).toBeGreaterThanOrEqual(4.5);
    expect(css).toMatch(/\.btn-primary\s*\{\s*@apply btn bg-primary-fill text-white/);
  });
});

describe("motion tokens", () => {
  it("defines three durations and the curves, in CSS and in Tailwind", () => {
    for (const name of [
      "duration-fast",
      "duration-normal",
      "duration-slow",
      "ease-standard",
      "ease-emphasized",
      "ease-sheet",
    ]) {
      expect(light[name], name).toBeTruthy();
    }
    const extend = config.theme?.extend as Record<string, Record<string, string>>;
    expect(Object.keys(extend.transitionDuration)).toEqual(["fast", "normal", "slow"]);
    expect(Object.keys(extend.transitionTimingFunction)).toEqual(
      expect.arrayContaining(["standard", "emphasized", "sheet", "ios"]),
    );
  });

  it("keeps the durations in order, so a bigger move never takes less time", () => {
    const ms = (n: string) => parseInt(String(light[n]), 10);
    expect(ms("duration-fast")).toBeLessThan(ms("duration-normal"));
    expect(ms("duration-normal")).toBeLessThan(ms("duration-slow"));
  });

  it("the shared button, input, card and link styles use the tokens, not loose numbers", () => {
    const components = css.slice(css.indexOf("@layer components"));
    expect(components).not.toMatch(/duration-(100|200|300)\b/);
  });

  it("switches animation and transitions off under prefers-reduced-motion, except spinners", () => {
    const rule = css.match(/@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\n\}\n/)?.[1] ?? "";
    expect(rule).toContain("animation-duration: 0.01ms !important");
    expect(rule).toContain("transition-duration: 0.01ms !important");
    expect(rule).toContain(":not(.animate-spin)");
  });
});
