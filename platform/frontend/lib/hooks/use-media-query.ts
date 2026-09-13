"use client";

/** Subscribes to a CSS media query from JavaScript.
 *
 * Read this before reaching for it: **the default is CSS, not this hook.** If
 * both shapes of a thing can sit in the DOM and CSS can pick which one shows,
 * do that (`md:hidden` / `hidden md:block`). `components/ui/data-list.tsx`
 * spells out why — no layout shift on hydration, no client/server mismatch, and
 * the two shapes cannot drift apart. This hook is for the cases where
 * JavaScript has to branch on *logic* rather than presentation: computing
 * absolute positions (the landing masonry), or genuinely not mounting an
 * expensive subtree.
 *
 * `useSyncExternalStore` rather than useEffect+useState: it takes an explicit
 * server snapshot, so the first client render matches the server HTML instead
 * of flipping on the first effect.
 */

import { useCallback, useSyncExternalStore } from "react";

/** Tailwind's default `screens`, mirrored — `tailwind.config.ts` deliberately
 * does not override them, so these stay in sync by being the same numbers. */
const BREAKPOINTS = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
} as const;

export type Breakpoint = keyof typeof BREAKPOINTS;

export function useMediaQuery(query: string, serverFallback = false): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    [query],
  );

  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => serverFallback,
  );
}

/** True from `bp` up — the JS equivalent of Tailwind's `md:` prefix.
 *
 * `serverFallback` defaults to false (mobile-first), matching how the
 * stylesheet reads: the unprefixed rules are the phone's. */
export function useBreakpoint(bp: Breakpoint, serverFallback = false): boolean {
  return useMediaQuery(`(min-width: ${BREAKPOINTS[bp]}px)`, serverFallback);
}
