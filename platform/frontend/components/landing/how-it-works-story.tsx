"use client";

/** "How it works" as a story told while you scroll, in the manner of Apple's product pages:
 * the five stages of a consultation are tall steps down the left, and the panel on the right
 * stays in view and changes to the stage that is at the middle of the screen.
 *
 * Below `lg` there is nothing to keep in view beside the steps, so each step carries its own
 * panel (CSS picks which shape shows, see platform/frontend/CLAUDE.md). The panel's stages
 * fade into each other in one grid cell, so it never changes height as the story advances. */

import { useEffect, useRef, useState } from "react";
import { WALKTHROUGH_STAGES } from "@/lib/landing-content";
import { useLanguage } from "@/lib/language";
import StageBody from "./stage-body";

export default function HowItWorksStory() {
  const { t } = useLanguage();
  const [active, setActive] = useState(0);
  const steps = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    // A thin band across the middle of the screen: the step inside it is the current one.
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries)
          if (entry.isIntersecting) setActive(Number((entry.target as HTMLElement).dataset.step));
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    for (const el of steps.current) if (el) observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-20">
      <ol aria-label={t("marketing.walkthrough.stagesLabel")}>
        {WALKTHROUGH_STAGES.map((stage, i) => (
          <li
            key={stage.id}
            ref={(el) => {
              steps.current[i] = el;
            }}
            data-step={i}
            className="flex flex-col justify-center py-8 lg:min-h-[55dvh]"
          >
            <span className="eyebrow text-primary-ink">{String(i + 1).padStart(2, "0")}</span>
            <h3
              data-active={i === active}
              className="mt-3 font-display text-[clamp(2rem,1.4rem+2vw,3.25rem)] font-light leading-[1.05] transition-opacity duration-normal ease-standard lg:data-[active=false]:opacity-40"
            >
              {t(stage.labelKey)}
            </h3>
            <div className="mt-6 rounded-[28px] border border-line/60 bg-card p-6 shadow-raised lg:hidden">
              <StageBody render={stage.render} t={t} />
            </div>
          </li>
        ))}
      </ol>

      <div className="hidden lg:block">
        <div
          data-story-panel
          className="sticky top-[calc(50dvh-14rem)] rounded-[28px] border border-line/60 bg-card p-8 shadow-raised-lg"
        >
          <div className="grid">
            {WALKTHROUGH_STAGES.map((stage, i) => (
              <div
                key={stage.id}
                aria-hidden={i !== active}
                className={`col-start-1 row-start-1 transition-opacity duration-slow ease-standard ${
                  i === active ? "opacity-100" : "pointer-events-none opacity-0"
                }`}
              >
                <StageBody render={stage.render} t={t} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
