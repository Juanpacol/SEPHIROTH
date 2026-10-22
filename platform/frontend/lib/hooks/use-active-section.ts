"use client";

import { useEffect, useState } from "react";

/** The id of the page section the reader is in, or null above the first one.
 *
 * A section counts as current while it crosses a thin band at the middle of the
 * screen, not when it is merely on screen: with the usual "most visible wins" rule,
 * a short section between two tall ones is never current, and the header would
 * point at the wrong place as you scroll past it. */
export function useActiveSection(ids: string[]): string | null {
  const [active, setActive] = useState<string | null>(null);
  const key = ids.join(",");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const elements = key
      .split(",")
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
          else setActive((current) => (current === entry.target.id ? null : current));
        }
      },
      { rootMargin: "-45% 0px -54% 0px" },
    );
    for (const el of elements) observer.observe(el);
    return () => observer.disconnect();
  }, [key]);

  return active;
}
