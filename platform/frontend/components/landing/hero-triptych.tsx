"use client";

/** The landing page's first screen: three full-height panels, each a picture of one of the things
 * SEPHIROTH does, with the headline set across all three. It follows the Ruby page's layout. Point
 * at (or focus, or tap) a panel and it widens, the others narrow, and a line says what it is. Nothing
 * plays by itself.
 *
 * The panels are the Ask, Verify and Share cells of the feature grid, with their pictures and words,
 * so the first screen and the grid cannot disagree. Below `md` they stack, all open. */

import { Fragment, useEffect, useRef, useState } from "react";
import { MotionConfig, motion } from "motion/react";
import { LANDING_FEATURES } from "@/lib/landing-features";
import { useLanguage } from "@/lib/language";
import CtaButton from "./cta-button";
import FeatureMediaView from "./feature-media";

const PANELS = ["ask", "verify", "share"] as const;
/** The last words of the headline are set in the brand blue, as the Ruby page sets its last word in red. */
const ACCENT_WORDS = 3;
/** A panel's widening is a spring, not a timed transition. A timed one restarts from rest whenever the pointer
 * moves to another panel, so a quick pass across the row stutters; a spring keeps the speed it already has
 * and swings towards the new target, which is what reads as smooth. */
const SPRING = { type: "spring", stiffness: 70, damping: 18, mass: 1.2 } as const;
/** How wide an open panel is against a closed one. */
const OPEN_GROW = 1.5;
/** How long the pointer rests on a panel before it opens. */
const INTENT_MS = 140;

export default function HeroTriptych() {
  const { t } = useLanguage();
  const [open, setOpen] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  /** A panel opens only after the pointer has settled on it, so crossing the row on the way to a button does
   * not make the panels flutter. */
  const openSoon = (id: string | null, delay = INTENT_MS) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(id), id === null ? 0 : delay);
  };
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const q = window.matchMedia("(min-width: 768px)");
    const sync = () => setWide(q.matches);
    sync();
    q.addEventListener("change", sync);
    return () => q.removeEventListener("change", sync);
  }, []);
  const canHover = () =>
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(hover: hover)").matches;
  const words = t("marketing.hero.title").split(" ");
  const features = PANELS.map((id) => LANDING_FEATURES.find((f) => f.id === id)!);

  return (
    <MotionConfig reducedMotion="user">
      <section data-hero className="relative overflow-hidden">
        <div
          data-hero-content
          className="relative min-h-[max(640px,100dvh)] translate-y-[calc(var(--hero-shift,0px)*0.25)] opacity-[calc(1-var(--hero-progress,0)*0.6)]"
        >
          {/* The three panels. */}
          <div className="absolute inset-0 flex flex-col md:flex-row" onMouseLeave={() => openSoon(null)}>
            {features.map((feature, i) => {
              const on = open === feature.id;
              return (
                <motion.article
                  key={feature.id}
                  animate={{ flexGrow: on && wide ? OPEN_GROW : 1 }}
                  transition={SPRING}
                  data-panel={feature.id}
                  data-open={on}
                  tabIndex={0}
                  aria-label={t(feature.titleKey)}
                  onMouseEnter={() => openSoon(feature.id)}
                  onFocus={() => openSoon(feature.id, 0)}
                  // A click only means something where there is no hover: a mouse already opened the panel by
                  // resting on it, and a click must not close it again and set the whole row moving.
                  onClick={() => {
                    if (!canHover()) openSoon(on ? null : feature.id, 0);
                  }}
                  className={`group relative min-h-0 min-w-0 flex-[1_1_0%] overflow-hidden border-l border-line/40 first:border-l-0`}
                >
                  {/* The picture has its own width, wider than a panel, so the panel opening uncovers more of it instead of
                    rescaling it: nothing in it moves while the panel grows. */}
                  <div className="absolute inset-y-0 left-1/2 w-[max(100%,46vw)] -translate-x-1/2 scale-[1.04] transition-transform duration-[1400ms] ease-[cubic-bezier(0.22,1,0.36,1)] group-data-[open=true]:scale-100">
                    <FeatureMediaView media={feature.media} />
                  </div>
                  {/* Darkens the picture toward the bottom, where the headline and the captions sit. */}
                  <div className="absolute inset-0 bg-gradient-to-t from-surface/90 via-surface/20 to-surface/40" />

                  <div className="relative z-10 flex h-full flex-col justify-between px-5 pb-6 pt-24 md:px-7 md:pb-8">
                    <div>
                      <div className="eyebrow text-white/80">
                        #{i + 1} {t(feature.verbKey)}
                      </div>
                    </div>
                    <div className="md:mb-28">
                      <p className="font-display text-2xl font-light leading-tight text-white md:text-3xl">
                        {t(feature.titleKey)}
                      </p>
                      <p className="mt-2 max-w-[22rem] text-sm leading-relaxed text-white/85 transition-[opacity,transform] duration-[700ms] delay-100 ease-standard md:absolute md:inset-x-7 md:bottom-8 md:translate-y-2 md:opacity-0 md:group-data-[open=true]:translate-y-0 md:group-data-[open=true]:opacity-100">
                        {t(feature.bodyKey)}
                      </p>
                    </div>
                  </div>
                </motion.article>
              );
            })}
          </div>

          {/* A shade across the top, so the header's text reads over any picture. */}
          <div className="pointer-events-none absolute inset-x-0 top-0 z-[15] h-44 bg-gradient-to-b from-surface/85 to-transparent" />

          {/* The headline, across all three. It does not catch the pointer, so the panels still do. */}
          <div className="pointer-events-none relative z-20 mx-auto flex min-h-[max(640px,100dvh)] max-w-7xl flex-col justify-center px-6 pb-48 pt-28 md:pb-60">
            <span className="eyebrow w-fit rounded-full border border-white/25 bg-surface/50 px-3 py-1 text-white/85 backdrop-blur-sm">
              {t("marketing.hero.badge")}
            </span>
            {/* A filter on the whole heading, not a text-shadow on each word: the shadow of a line would
              fall over the bottom of the line above it and read as a smear under its letters. */}
            <h1 className="mt-5 flex max-w-5xl flex-wrap gap-x-[0.22em] font-display text-[clamp(3rem,1rem+5.8vw,7.5rem)] font-light uppercase leading-[0.92] text-white [filter:drop-shadow(0_2px_24px_rgb(0_0_0/0.4))]">
              {words.map((word, i) => (
                <Fragment key={i}>
                  <span
                    style={{ animationDelay: `${i * 60}ms` }}
                    className={`inline-block animate-word-in [animation-fill-mode:both] ${
                      i >= words.length - ACCENT_WORDS ? "text-[#b6cfff]" : ""
                    }`}
                  >
                    {word}
                  </span>
                  {/* A space between the words, for the text that is read and copied: a flex container draws none. */}{" "}
                </Fragment>
              ))}
            </h1>
            <p className="mt-5 max-w-2xl text-lg text-white/85 [text-shadow:0_1px_14px_rgb(0_0_0/0.5)]">
              {t("marketing.hero.subtitle")}
            </p>
            <div className="pointer-events-auto mt-8 flex flex-wrap items-center gap-3">
              <CtaButton href="/login">{t("marketing.openApp")}</CtaButton>
              <CtaButton href="#how-it-works" variant="line">
                {t("marketing.hero.seeHowItWorks")}
              </CtaButton>
            </div>
          </div>
        </div>
      </section>
    </MotionConfig>
  );
}
