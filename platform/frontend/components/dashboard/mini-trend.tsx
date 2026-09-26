const WIDTH = 96;
const HEIGHT = 24;
const PADDING = 3;

export type TrendTone = "danger" | "warning" | "neutral";

const DOT_CLASS: Record<TrendTone, string> = {
  danger: "fill-danger",
  warning: "fill-warning",
  neutral: "fill-ink/50",
};

/** A minimal trend line, oldest -> newest left to right. The axis follows the
 * values themselves, so one wildly abnormal point does not flatten the rest.
 * Draws nothing below two points: a single reading is not a trend. */
export default function MiniTrend({
  values,
  lastTone = "neutral",
  label,
}: {
  values: number[];
  lastTone?: TrendTone;
  label: string;
}) {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const innerW = WIDTH - PADDING * 2;
  const innerH = HEIGHT - PADDING * 2;
  const y = (v: number) => PADDING + innerH - ((v - min) / span) * innerH;
  const points = values
    .map((v, i) => `${(PADDING + (i / (values.length - 1)) * innerW).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");

  return (
    <svg
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="shrink-0"
      role="img"
      aria-label={label}
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        className="text-ink/30"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={PADDING + innerW} cy={y(values[values.length - 1])} r={2.5} className={DOT_CLASS[lastTone]} />
    </svg>
  );
}
