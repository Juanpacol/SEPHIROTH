import React, { type CSSProperties } from "react";

import { cn } from "@/lib/utils";

/** Vendored from magicui.design, ported to Tailwind v3: `@container-[size]`
 * (v4-only container-query utility) becomes a plain `[container-type:size]`
 * arbitrary property — v3 supports arbitrary CSS properties natively, just
 * not the shorthand container-query *utility* v4 added. `inset-(--cut)`
 * (v4 shorthand) becomes an inline style. Default `background` changed
 * from magicui's black to the app's own primary blue.
 *
 * Also adds an optional `href`: the landing page that uses this is a
 * Server Component, which can't pass an `onClick` closure down to a client
 * leaf (functions aren't serializable across that boundary) — rendering a
 * plain `<a>` instead of a `<button>` when `href` is given sidesteps that
 * without converting the whole page to a Client Component. */

export interface ShimmerButtonProps {
  shimmerColor?: string;
  shimmerSize?: string;
  borderRadius?: string;
  shimmerDuration?: string;
  background?: string;
  className?: string;
  children?: React.ReactNode;
  href?: string;
  onClick?: () => void;
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
}

export const ShimmerButton = React.forwardRef<HTMLButtonElement, ShimmerButtonProps>(
  (
    {
      shimmerColor = "#ffffff",
      shimmerSize = "0.08em",
      shimmerDuration = "2.5s",
      borderRadius = "1rem",
      background = "#3683F8",
      className,
      children,
      href,
      ...props
    },
    ref
  ) => {
    const Tag = href ? "a" : "button";
    return (
      <Tag
        href={href}
        style={
          {
            "--spread": "90deg",
            "--shimmer-color": shimmerColor,
            "--radius": borderRadius,
            "--speed": shimmerDuration,
            "--cut": shimmerSize,
            "--bg": background,
          } as CSSProperties
        }
        className={cn(
          "group relative z-0 flex cursor-pointer items-center justify-center gap-2 overflow-hidden whitespace-nowrap px-4 py-2.5 text-sm font-semibold text-white [background:var(--bg)] [border-radius:var(--radius)]",
          "transform-gpu transition-transform duration-200 ease-ios active:translate-y-px active:scale-[0.97]",
          className
        )}
        ref={ref as React.Ref<HTMLAnchorElement & HTMLButtonElement>}
        {...props}
      >
        <div className="absolute inset-0 -z-30 overflow-visible blur-[2px] [container-type:size]">
          <div className="animate-shimmer-slide absolute inset-0 aspect-square h-[100cqh] rounded-none">
            <div className="animate-spin-around absolute -inset-full w-auto rotate-0 [background:conic-gradient(from_calc(270deg-(var(--spread)*0.5)),transparent_0,var(--shimmer-color)_var(--spread),transparent_var(--spread))]" />
          </div>
        </div>

        {children}

        <div className="absolute inset-0 size-full [border-radius:var(--radius)] shadow-[inset_0_-8px_10px_#ffffff1f] transition-all duration-200 ease-ios group-hover:shadow-[inset_0_-6px_10px_#ffffff3f] group-active:shadow-[inset_0_-10px_10px_#ffffff3f]" />

        <div className="absolute -z-20 [border-radius:var(--radius)] [background:var(--bg)]" style={{ inset: "var(--cut)" }} />
      </Tag>
    );
  }
);

ShimmerButton.displayName = "ShimmerButton";
