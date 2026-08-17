/** SEPHIROTH's brand mark — an original single-wing signature, not a
 * drawing of any character or logo. Every path is arithmetic, drawn on a
 * 24x24 grid:
 *
 *   1. Spine: one quadratic arc from the shoulder (4,20) to the tip
 *      (21,4) via control point (9,7) — `M4 20 Q9 7 21 4`. A taut
 *      upward sweep, biased right (one wing, asymmetric by definition).
 *   2. Feathers: 4 ribs dropping from evenly-spaced points along the
 *      spine, each a short quadratic curve ending on a trailing-edge arc
 *      `M6.5 21 Q13 16 21 9.5`. Rib length shrinks root-to-tip; each
 *      rib's control point is offset toward the shoulder for the
 *      feather-curl look.
 *   3. Negative space between ribs stays >=1.6 units at 24px — the
 *      number that decides whether it survives shrinking to a favicon
 *      (see `app/icon.svg`, which uses a simplified 2-rib form instead).
 *
 * Stroke-based, `currentColor` — never gradient-filled. The `sephiroth`
 * gradient is reserved as the "this is AI-generated" signal elsewhere in
 * the app; diluting it onto the brand mark itself would break that
 * meaning (CLAUDE.md decision #4).
 */
export default function WingMark({ size = 24, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M4 20 Q9 7 21 4" />
      <path d="M6.5 21 Q13 16 21 9.5" />
      <path d="M6 19.4 Q7.6 18.2 8.6 16.4" />
      <path d="M8.2 17.6 Q10 16.6 11.2 14.6" />
      <path d="M10.6 15.6 Q12.1 14.8 13 13.1" />
      <path d="M13 13.4 Q14.2 12.8 15 11.4" />
    </svg>
  );
}
