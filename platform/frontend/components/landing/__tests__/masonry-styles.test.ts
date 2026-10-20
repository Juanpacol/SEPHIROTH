import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/** The gallery's look is in one stylesheet. These read it as text, because a
 * unit test has no layout engine to ask whether a caption is visible: they pin
 * the rules that decide it, so a change that brings the old behaviour back fails. */
const css = readFileSync(path.join(__dirname, "..", "masonry.module.css"), "utf8");

/** The rule body for `selector`, or "" when there is none. Comments are dropped. */
function rule(selector: string, source = css.replace(/\/\*[\s\S]*?\*\//g, "")): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`, "m").exec(source)?.[1] ?? "";
}

const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
const hoverBlock = /@media \(hover: hover\) \{([\s\S]*?)\n\}/.exec(stripped)?.[1] ?? "";

describe("masonry.module.css", () => {
  it("shows the caption by default, so a phone sees it", () => {
    expect(rule(".caption")).toMatch(/opacity:\s*1/);
  });

  it("hides the caption until hover or focus only where a pointer can hover", () => {
    expect(hoverBlock).toMatch(/\.caption\s*\{[^}]*opacity:\s*0/);
    expect(hoverBlock).toMatch(/\.itemWrapper:hover \.caption/);
    expect(hoverBlock).toMatch(/\.itemWrapper:focus-visible \.caption/);
    expect(hoverBlock).toMatch(/\.itemWrapper:focus-within \.caption/);
  });

  it("does not hide the caption anywhere outside that media query", () => {
    expect(stripped.replace(hoverBlock, "")).not.toMatch(/\.caption\s*\{[^}]*opacity:\s*0\b/);
  });

  it("is not a pointer cursor unless the card is a link", () => {
    expect(rule(".itemWrapper")).toMatch(/cursor:\s*default/);
    expect(rule(".link")).toMatch(/cursor:\s*pointer/);
    expect(stripped.match(/cursor:\s*pointer/g)).toHaveLength(1);
  });

  it("keeps no permanent will-change and no transition on everything", () => {
    expect(stripped).not.toMatch(/will-change/);
    expect(stripped).not.toMatch(/transition:\s*all/);
  });

  it("stacks its shadows, from a contact shadow to an ambient one", () => {
    const shadow = rule(".itemImg").match(/box-shadow:([^;]*);/)?.[1] ?? "";
    expect(shadow.split("rgba(").length - 1).toBeGreaterThanOrEqual(3);
  });

  it("puts a 1px white edge over the image, not a tint", () => {
    const edge = rule(".itemImg::after");
    expect(edge).toMatch(/inset 0 0 0 1px rgba\(255,\s*255,\s*255,/);
    expect(edge).toMatch(/pointer-events:\s*none/);
  });

  it("gives a keyboard user a visible ring, and a high-contrast user a real border", () => {
    expect(rule(".itemWrapper:focus-visible .itemImg")).toMatch(/outline:\s*2px solid/);
    expect(stripped).toMatch(/@media \(forced-colors: active\)[\s\S]*border:\s*1px solid CanvasText/);
  });
});
