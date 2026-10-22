/** The maths behind the landing page's scroll-linked motion: where a piece of the page is
 * in its animation, as a number from 0 to 1, given only where the reader is. Pure, so
 * it can be tested; `components/landing/scroll-effects.tsx` reads the page and writes
 * the results to CSS variables.
 *
 * The idea is borrowed from the Hermes Agent site, which drives its footer reveal, hero
 * and parallax from the scroll position instead of from timers: the motion is exactly
 * as far along as the reader is, and stops when they stop. */

export const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
export const clamp01 = (value: number) => clamp(value, 0, 1);

/** How far the footer has come into view: 0 while its top edge is still at the bottom of
 * the screen, 1 once about nine tenths of it (at most one screen) is showing. */
export function footerProgress(args: {
  scrollY: number;
  viewportHeight: number;
  footerTop: number;
  footerHeight: number;
}): number {
  const { scrollY, viewportHeight, footerTop, footerHeight } = args;
  const reveal = Math.max(1, Math.min(footerHeight, viewportHeight) * 0.9);
  return clamp01((scrollY + viewportHeight - footerTop) / reveal);
}

/** How far the hero has scrolled away, eased: slow at first, so the headline holds until
 * the reader has clearly left it. */
export function heroProgress(scrollY: number, heroHeight: number): number {
  return clamp01(scrollY / Math.max(1, heroHeight)) ** 2;
}

/** How far the hero's content has drifted down, in px: it travels at a third of the scroll
 * speed, so it seems further away than the page, up to one screen. */
export function heroShift(scrollY: number, viewportHeight: number): number {
  return clamp(0.35 * scrollY, 0, viewportHeight);
}

/** The footer's rise, in px: it starts `distance` below its place and settles with an
 * ease-out, so most of the travel happens as it first appears and the last stretch is
 * gentle. (Quadratic: the remaining distance is the square of the remaining progress.) */
export function footerLift(progress: number, distance: number): number {
  return distance * (1 - clamp01(progress)) ** 2;
}

/** How far a picture drifts inside its frame, in px, given where the frame is on screen.
 * At the middle of the screen it is 0; entering from below it is held `strength` of the
 * frame's height back, and leaving at the top it is that far forward, so the picture
 * moves a little slower than the page. The picture has to be larger than its frame by at
 * least `strength` on each side, or the drift would show an edge. */
export function parallaxShift(args: {
  frameTop: number;
  frameHeight: number;
  viewportHeight: number;
  strength?: number;
}): number {
  const { frameTop, frameHeight, viewportHeight, strength = 0.1 } = args;
  const offset = frameTop + frameHeight / 2 - viewportHeight / 2;
  const range = viewportHeight / 2 + frameHeight / 2;
  return -(clamp(offset / Math.max(1, range), -1, 1) * frameHeight * strength);
}

/** One step of exponential smoothing toward `target`, frame-rate independent: the value
 * covers the same share of the remaining distance per second whatever `dt` is. This is
 * the "delay": the page does not jump to where the scroll is, it follows it. */
export function damp(current: number, target: number, dt: number, rate = 9): number {
  return current + (target - current) * (1 - Math.exp(-rate * dt));
}
