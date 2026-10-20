/** Where each card of the landing gallery goes, as a pure function.
 *
 * Card heights are fixed numbers, not a function of the container's width, so
 * the height of the whole gallery depends only on how many columns there are.
 * That is what lets the page reserve exactly the right height before anything
 * is measured: `components/landing/analysis-gallery.module.css` holds those
 * heights per breakpoint, and `components/landing/__tests__/gallery-height.test.ts`
 * fails if they stop matching this function. Reserving a guess instead (it used
 * to be 640px) made everything below the gallery jump, and, behind a height
 * transition, slide down the page, every time someone opened the landing page.
 */

export interface PlaceableItem {
  height: number;
}

export interface Placed<T> {
  item: T;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Shortest column first, in item order: the masonry rule. */
export function placeItems<T extends PlaceableItem>(items: T[], columns: number, width: number): Placed<T>[] {
  const colHeights = new Array(columns).fill(0);
  const columnWidth = width / columns;

  return items.map((item) => {
    const col = colHeights.indexOf(Math.min(...colHeights));
    const h = item.height / 2;
    const placed = { item, x: columnWidth * col, y: colHeights[col], w: columnWidth, h };
    colHeights[col] += h;
    return placed;
  });
}

/** The tallest column: the height the gallery needs. Independent of width. */
export function layoutHeight(items: PlaceableItem[], columns: number): number {
  return Math.max(...placeItems(items, columns, 1).map((p) => p.y + p.h));
}

/** Viewport breakpoints (min-width, px) at which the column count steps up:
 * one column on a phone, five on a wide desktop. */
export const COLUMN_BREAKPOINTS = [
  { minWidth: 400, columns: 2 },
  { minWidth: 600, columns: 3 },
  { minWidth: 1000, columns: 4 },
  { minWidth: 1500, columns: 5 },
] as const;
