import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import config from "../../tailwind.config";

/** The interaction rules in globals.css and tailwind.config.ts, read as text so a
 * change that drops one (a sticky hover, a missing focus ring, an animation that
 * ignores the motion tokens) fails here. */
const css = readFileSync(path.join(__dirname, "../../app/globals.css"), "utf8");
const extend = config.theme?.extend as Record<string, Record<string, unknown>>;

describe("hover", () => {
  it("applies only where the device can hover, so a tap never leaves a button lifted", () => {
    expect(config.future).toMatchObject({ hoverOnlyWhenSupported: true });
  });

  it("draws the button arc only for pointer devices, and only on an enabled button", () => {
    const media = css.match(/@media \(hover: hover\)\s*\{([\s\S]*?)\n  \}/)?.[1] ?? "";
    expect(media).toContain(".btn-primary:hover:not(:disabled)::after");
    expect(media).toContain(".btn-secondary:hover:not(:disabled)::after");
    expect(css).toMatch(/\.btn-primary::after,\s*\.btn-secondary::after\s*\{[^}]*opacity: 0;/);
  });

  it("paints the arc as a hairline ring, so it adds no size and no layout", () => {
    const rule = css.match(/\.btn-primary::after,\s*\.btn-secondary::after\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toContain("position: absolute");
    expect(rule).toContain("pointer-events: none");
    expect(rule).toMatch(/mask:/);
  });

  it("gives buttons a pressed state", () => {
    expect(css).toMatch(/\.btn-primary\s*\{[^}]*active:shadow-\[inset/);
    expect(css).toMatch(/\.btn-secondary\s*\{[^}]*active:shadow-\[inset/);
  });
});

describe("focus", () => {
  it("is visible with the keyboard on everything that takes focus, in one style", () => {
    const rule = css.match(/:where\(([^)]*)\):focus-visible\s*\{([^}]*)\}/);
    expect(rule?.[1]).toEqual(expect.stringContaining("button"));
    expect(rule?.[1]).toEqual(expect.stringContaining("a"));
    expect(rule?.[1]).toEqual(expect.stringContaining("select"));
    expect(rule?.[1]).toEqual(expect.stringContaining('[role="tab"]'));
    expect(rule?.[2]).toContain("outline: 2px solid rgb(var(--color-primary-ink))");
    expect(rule?.[2]).toContain("outline-offset: 2px");
  });
});

describe("motion", () => {
  it("every enter and leave animation takes its duration and curve from the tokens", () => {
    const animations = extend.animation as Record<string, string>;
    const named = Object.entries(animations).filter(([k]) => /^(toast|scrim|sheet)-/.test(k));
    expect(named.map(([k]) => k)).toEqual(
      expect.arrayContaining([
        "toast-in",
        "toast-out",
        "scrim-in",
        "scrim-out",
        "sheet-in-right",
        "sheet-out-bottom",
      ]),
    );
    for (const [name, value] of named) {
      expect(value, name).toMatch(/var\(--duration-(fast|normal|slow)\)/);
      expect(value, name).toMatch(/var\(--ease-(standard|emphasized|sheet)\)/);
    }
  });

  it("leaves are never slower than the matching enters", () => {
    const animations = extend.animation as Record<string, string>;
    const rank = { fast: 1, normal: 2, slow: 3 } as const;
    const ms = (n: string) => rank[animations[n].match(/--duration-(\w+)/)![1] as keyof typeof rank];
    for (const [enter, leave] of [
      ["toast-in", "toast-out"],
      ["scrim-in", "scrim-out"],
      ["sheet-in-right", "sheet-out-right"],
      ["sheet-in-left", "sheet-out-left"],
      ["sheet-in-bottom", "sheet-out-bottom"],
    ]) {
      expect(ms(leave), `${leave} vs ${enter}`).toBeLessThanOrEqual(ms(enter));
    }
  });

  it("enters travel a few pixels, never from off screen", () => {
    const keyframes = JSON.stringify(extend.keyframes);
    const offsets = Array.from(keyframes.matchAll(/translate[XY]\((-?\d+)px\)/g)).map((m) =>
      Math.abs(Number(m[1])),
    );
    expect(Math.max(...offsets)).toBeLessThanOrEqual(24);
  });
});
