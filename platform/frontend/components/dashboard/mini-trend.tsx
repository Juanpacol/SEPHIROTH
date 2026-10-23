"use client";

import { useEffect, useId, useState } from "react";

const WIDTH = 132;
const HEIGHT = 34;
const PADDING = 4;

export type TrendTone = "danger" | "warning" | "neutral";

const DOT_CLASS: Record<TrendTone, string> = {
  danger: "fill-danger",
  warning: "fill-warning",
  neutral: "fill-ink/50",
};

const HALO_CLASS: Record<TrendTone, string> = {
  danger: "fill-danger/25",
  warning: "fill-warning/25",
  neutral: "fill-ink/10",
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
  const gradient = useId();
  // The line draws itself left to right once mounted (instant under reduced motion).
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setDrawn(true));
    return () => cancelAnimationFrame(id);
  }, []);
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

  const last = { x: PADDING + innerW, y: y(values[values.length - 1]) };
  const area = `${PADDING},${HEIGHT} ${points} ${last.x},${HEIGHT}`;

  return (
    <svg
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="shrink-0 overflow-visible text-primary-ink"
      role="img"
      aria-label={label}
    >
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="currentColor" stopOpacity="0.28" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={area}
        fill={`url(#${gradient})`}
        className={`transition-opacity duration-[900ms] delay-300 ${drawn ? "opacity-100" : "opacity-0"}`}
      />
      <polyline
        points={points}
        pathLength={1}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinejoin="round"
        strokeLinecap="round"
        strokeDasharray={1}
        strokeDashoffset={drawn ? 0 : 1}
        className="transition-[stroke-dashoffset] duration-[1000ms] ease-[cubic-bezier(0.22,1,0.36,1)]"
      />
      <circle
        cx={last.x}
        cy={last.y}
        r={3}
        className={`${DOT_CLASS[lastTone]} transition-opacity duration-300 delay-[900ms] ${drawn ? "opacity-100" : "opacity-0"}`}
      />
      <circle cx={last.x} cy={last.y} r={6} className={`${HALO_CLASS[lastTone]} motion-safe:animate-pulse`} />
    </svg>
  );
}
