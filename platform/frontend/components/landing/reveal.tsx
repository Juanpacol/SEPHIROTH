"use client";

/** Brings a block in as it is first scrolled to: it rises a little and fades in, once. Only opacity and a
 * transform change, so nothing around it moves.
 *
 * It is never hidden for a reader who cannot see it come in. Until the page has run, with no
 * IntersectionObserver, with reduced motion, or when the block is already on screen at load, it is simply
 * shown. Only a block that starts below the fold is held back, and only after mount, so a page whose script
 * fails still has all its content. `delay` staggers neighbours (ms). `data-state` is `hidden` or `shown`. */

import { useEffect, useRef, useState, type ElementType, type ReactNode } from "react";

type State = "pending" | "hidden" | "shown";

export function useReveal<T extends HTMLElement>(): { ref: React.RefObject<T>; state: State } {
  const ref = useRef<T>(null);
  const [state, setState] = useState<State>("pending");

  useEffect(() => {
    const el = ref.current;
    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!el || reduced || typeof IntersectionObserver === "undefined") {
      setState("shown");
      return;
    }
    // Already in view at load: nothing to reveal.
    if (el.getBoundingClientRect().top < window.innerHeight * 0.9) {
      setState("shown");
      return;
    }
    setState("hidden");
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setState("shown");
          observer.disconnect();
        }
      },
      { rootMargin: "0px 0px -12% 0px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, state };
}

export default function Reveal({
  as,
  delay = 0,
  className = "",
  children,
}: {
  as?: ElementType;
  delay?: number;
  className?: string;
  children: ReactNode;
}) {
  const Tag = (as ?? "div") as ElementType;
  const { ref, state } = useReveal<HTMLElement>();
  return (
    <Tag
      ref={ref}
      data-reveal={state}
      style={{ transitionDelay: state === "shown" ? `${delay}ms` : "0ms" }}
      className={`transition-[opacity,transform] duration-[800ms] ease-[cubic-bezier(0.22,1,0.36,1)] data-[reveal=hidden]:translate-y-8 data-[reveal=hidden]:opacity-0 ${className}`}
    >
      {children}
    </Tag>
  );
}
