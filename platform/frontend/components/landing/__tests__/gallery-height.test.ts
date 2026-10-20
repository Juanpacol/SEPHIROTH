import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ITEMS } from "@/components/landing/analysis-gallery";
import { COLUMN_BREAKPOINTS, layoutHeight } from "@/lib/masonry-layout";

/** The gallery's height is stated in CSS so the page reserves the right amount of
 * room before the cards are placed. If those numbers drift from what the layout
 * really needs, everything below the gallery jumps on load again. */
const here = (file: string) => readFileSync(path.join(__dirname, "..", file), "utf8");
const css = here("analysis-gallery.module.css").replace(/\/\*[\s\S]*?\*\//g, "");
const gallery = here("analysis-gallery.tsx");
const masonry = here("masonry.tsx");

/** The `.stage` height declared at (and above) a given viewport width. */
function declaredHeight(minWidth: number | null): number {
  const block =
    minWidth === null
      ? css.slice(0, css.indexOf("@media"))
      : new RegExp(`@media \\(min-width: ${minWidth}px\\) \\{([\\s\\S]*?)\\n\\}`).exec(css)?.[1] ?? "";
  return Number(/height:\s*(\d+)px/.exec(block)?.[1]);
}

describe("the gallery's reserved height", () => {
  it("is right for a phone, one column", () => {
    expect(declaredHeight(null)).toBe(layoutHeight(ITEMS, 1));
  });

  it.each(COLUMN_BREAKPOINTS.map((b) => [b.minWidth, b.columns]))(
    "is right from %ipx up, with %i columns",
    (minWidth, columns) => {
      expect(declaredHeight(minWidth)).toBe(layoutHeight(ITEMS, columns));
    },
  );

  it("steps at the same widths the layout changes its column count", () => {
    for (const { minWidth } of COLUMN_BREAKPOINTS) {
      expect(masonry).toContain(`(min-width:${minWidth}px)`);
    }
  });

  it("is applied through the stylesheet, not measured and set in state", () => {
    expect(gallery).toContain("styles.stage");
    expect(gallery).not.toMatch(/useState|setContentHeight|handleLayout|onLayout/);
  });

  it("does not slide the page: no height transition on the gallery", () => {
    expect(gallery).not.toMatch(/transition:\s*["'`]height/);
    expect(css).not.toMatch(/transition/);
  });
});
