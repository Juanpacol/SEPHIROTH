"use client";

/** The landing page's feature grid, in the manner of the Hermes Agent site: three columns
 * and two rows, each cell a numbered label (`#1 ASK`), a title in the display face, a
 * paragraph and a square picture under it. Below `lg` it is two columns, then one.
 *
 * The cells come from `lib/landing-features.ts`, where each feature's picture, video or
 * generated tile is chosen. A cell's video plays only while the cell is on screen. */

import { useEffect, useRef, useState } from "react";
import { LANDING_FEATURES } from "@/lib/landing-features";
import { useLanguage } from "@/lib/language";
import FeatureMediaView from "./feature-media";
import Reveal from "./reveal";

export default function FeatureShowcase() {
  const { t } = useLanguage();
  const [inView, setInView] = useState<Record<string, boolean>>({});
  const cells = useRef<Record<string, HTMLElement | null>>({});

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        setInView((current) => {
          const next = { ...current };
          for (const entry of entries)
            next[(entry.target as HTMLElement).dataset.feature ?? ""] = entry.isIntersecting;
          return next;
        });
      },
      { threshold: 0.35 },
    );
    for (const el of Object.values(cells.current)) if (el) observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <ol className="grid grid-cols-1 gap-x-10 gap-y-20 md:grid-cols-2 lg:grid-cols-3">
      {LANDING_FEATURES.map((feature, i) => (
        <Reveal as="li" key={feature.id} delay={(i % 3) * 120}>
          <article
            id={`feature-${feature.id}`}
            data-feature={feature.id}
            ref={(el) => {
              cells.current[feature.id] = el;
            }}
            aria-labelledby={`feature-${feature.id}-title`}
            className="group/cell flex h-full flex-col"
          >
            <div className="eyebrow text-ink/80">
              #{i + 1} {t(feature.verbKey)}
            </div>
            <h3
              id={`feature-${feature.id}-title`}
              className="mt-5 font-display text-[clamp(2.5rem,1.6rem+2.4vw,3.75rem)] font-light leading-[1.02]"
            >
              {t(feature.titleKey)}
            </h3>
            <p className="mt-6 max-w-[34ch] text-lg font-light leading-relaxed text-ink/90 md:text-xl">
              {t(feature.bodyKey)}
            </p>
            {/* `mt-auto`: the picture sits at the bottom of the cell, so the six line up by their
                pictures whatever number of lines a title or a paragraph takes. */}
            <div className="mt-auto pt-8 md:pt-10">
              <div
                data-parallax-frame
                className="aspect-square overflow-hidden bg-surface [&_img]:transition-transform [&_img]:duration-[1200ms] [&_img]:ease-[cubic-bezier(0.22,1,0.36,1)] group-hover/cell:[&_img]:scale-[1.04]"
              >
                <FeatureMediaView media={feature.media} playing={Boolean(inView[feature.id])} />
              </div>
            </div>
          </article>
        </Reveal>
      ))}
    </ol>
  );
}
