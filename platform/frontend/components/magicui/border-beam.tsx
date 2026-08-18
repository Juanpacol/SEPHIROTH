"use client";

/** Vendored from magicui.design, ported to Tailwind v3: the original uses
 * v4-only utilities (`border-(length:--x)`, `mask-*`, `bg-linear-to-l
 * from-(--x)`) that don't exist in v3. Same visual result — a light beam
 * traveling around a card's border via `offset-path` — expressed as plain
 * inline styles instead, since the underlying CSS properties (masking,
 * gradients) work identically either way. */

import { motion, type MotionStyle, type Transition } from "motion/react";

import { cn } from "@/lib/utils";

interface BorderBeamProps {
  size?: number;
  duration?: number;
  delay?: number;
  colorFrom?: string;
  colorTo?: string;
  transition?: Transition;
  className?: string;
  style?: React.CSSProperties;
  reverse?: boolean;
  initialOffset?: number;
  borderWidth?: number;
}

export const BorderBeam = ({
  className,
  size = 50,
  delay = 0,
  duration = 6,
  colorFrom = "#3683F8",
  colorTo = "#8C92AC",
  transition,
  style,
  reverse = false,
  initialOffset = 0,
  borderWidth = 1.5,
}: BorderBeamProps) => {
  return (
    <div
      className="pointer-events-none absolute inset-0 rounded-[inherit] border-transparent"
      style={{
        borderWidth,
        borderStyle: "solid",
        maskImage: "linear-gradient(transparent, transparent), linear-gradient(#000, #000)",
        maskComposite: "intersect",
        WebkitMaskComposite: "source-in",
        maskClip: "padding-box, border-box",
      }}
    >
      <motion.div
        className={cn("absolute aspect-square", className)}
        style={
          {
            width: size,
            offsetPath: `rect(0 auto auto 0 round ${size}px)`,
            background: `linear-gradient(to left, ${colorFrom}, ${colorTo}, transparent)`,
            ...style,
          } as MotionStyle
        }
        initial={{ offsetDistance: `${initialOffset}%` }}
        animate={{
          offsetDistance: reverse
            ? [`${100 - initialOffset}%`, `${-initialOffset}%`]
            : [`${initialOffset}%`, `${100 + initialOffset}%`],
        }}
        transition={{
          repeat: Infinity,
          ease: "linear",
          duration,
          delay: -delay,
          ...transition,
        }}
      />
    </div>
  );
};
