import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import config from "../../tailwind.config";

/** The two interaction rules that protect people: hover only where a device can hover, and a
 * visible keyboard focus ring. (The button arc, the pressed state and the motion tokens used to be
 * pinned here too: they described a look, and failed on any change of it.) */
const css = readFileSync(path.join(__dirname, "../../app/globals.css"), "utf8");

describe("hover", () => {
  it("applies only where the device can hover, so a tap never leaves a button lifted", () => {
    expect(config.future).toMatchObject({ hoverOnlyWhenSupported: true });
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
