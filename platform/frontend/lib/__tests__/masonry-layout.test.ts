import { describe, expect, it } from "vitest";
import { COLUMN_BREAKPOINTS, layoutHeight, placeItems } from "@/lib/masonry-layout";

const items = (...heights: number[]) => heights.map((height, i) => ({ id: i, height }));

describe("placeItems", () => {
  it("puts each card in the shortest column, in order", () => {
    const placed = placeItems(items(400, 200, 200, 200), 2, 1000);

    // Items 2 and 3 go under the second card (100, then 200 tall); item 4 finds the
    // two columns tied at 200 and the first column wins.
    expect(placed.map((p) => [p.x, p.y])).toEqual([
      [0, 0],
      [500, 0],
      [500, 100],
      [0, 200],
    ]);
  });

  it("halves each height, because the gallery is laid out at half the nominal size", () => {
    expect(placeItems(items(560), 1, 800)[0]).toMatchObject({ h: 280, w: 800 });
  });

  it("divides the width evenly between the columns", () => {
    const placed = placeItems(items(10, 10, 10), 3, 900);

    expect(placed.map((p) => p.w)).toEqual([300, 300, 300]);
    expect(placed.map((p) => p.x)).toEqual([0, 300, 600]);
  });
});

describe("layoutHeight", () => {
  it("is the tallest column", () => {
    expect(layoutHeight(items(400, 200, 200, 200), 2)).toBe(300);
    expect(layoutHeight(items(400, 200, 200, 200), 1)).toBe(500);
  });

  it("does not depend on the width, which is what makes it knowable before anything is measured", () => {
    const list = items(540, 560, 440, 760, 460);

    const heights = [200, 800, 1450].map((width) => Math.max(...placeItems(list, 3, width).map((p) => p.y + p.h)));

    expect(new Set(heights).size).toBe(1);
    expect(heights[0]).toBe(layoutHeight(list, 3));
  });

  it("never grows when there are more columns", () => {
    const list = items(540, 560, 440, 760, 460, 380, 500);

    const byColumns = [1, 2, 3, 4, 5].map((c) => layoutHeight(list, c));

    expect([...byColumns].sort((a, b) => b - a)).toEqual(byColumns);
  });
});

describe("COLUMN_BREAKPOINTS", () => {
  it("steps from two columns at 400px to five at 1500px, in order", () => {
    expect(COLUMN_BREAKPOINTS.map((b) => [b.minWidth, b.columns])).toEqual([
      [400, 2],
      [600, 3],
      [1000, 4],
      [1500, 5],
    ]);
  });
});
