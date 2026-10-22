"use client";

/**
 * The landing page. One hard rule enforced throughout: the `sephiroth`
 * gradient (`bg-sephiroth` / `.ai-badge` / `.ai-ring`) means "this content
 * is AI-generated" everywhere else in the app — it appears here ONLY on
 * the mock AI-output cards inside the interactive walkthroughs (the
 * Coordinator draft, the abstention-gate answer). The hero, nav, section
 * headers, and the brand mark itself use `primary`/`ink`/`line`, never
 * the gradient — diluting it here would break that signal everywhere
 * else. Don't "brighten it up."
 */

import Link from "next/link";
import { ScanEye } from "lucide-react";
import WingMark from "@/components/brand/wing-mark";
import AuthRedirectGate from "@/components/landing/auth-redirect-gate";
import ScrollEffects from "@/components/landing/scroll-effects";
import AnswerCard from "@/components/landing/answer-card";
import FeatureShowcase from "@/components/landing/feature-showcase";
import HowItWorksStory from "@/components/landing/how-it-works-story";
import TrustCarousel from "@/components/landing/trust-carousel";
import ChapterStrip from "@/components/landing/chapter-strip";
import { TextAnimate } from "@/components/magicui/text-animate";
import { ShimmerButton } from "@/components/magicui/shimmer-button";
import { useLanguage } from "@/lib/language";

const FAQS = [
  { qKey: "marketing.faq.q1", aKey: "marketing.faq.a1" },
  { qKey: "marketing.faq.q2", aKey: "marketing.faq.a2" },
  { qKey: "marketing.faq.q3", aKey: "marketing.faq.a3" },
  { qKey: "marketing.faq.q4", aKey: "marketing.faq.a4" },
  { qKey: "marketing.faq.q5", aKey: "marketing.faq.a5" },
];

export default function LandingPage() {
  const { t } = useLanguage();
  return (
    <>
      <AuthRedirectGate />
      <ScrollEffects />

      {/* Hero: the headline and the way in on one side, an answer as the product gives it on the other */}
      <section data-hero className="band-dark relative overflow-hidden">
        <div
          data-hero-content
          className="relative mx-auto grid max-w-7xl translate-y-[calc(var(--hero-shift,0px)*0.45)] items-center gap-14 px-6 py-24 opacity-[calc(1-var(--hero-progress,0)*0.7)] md:py-32 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-16"
        >
          <WingMark
            size={420}
            className="pointer-events-none absolute left-1/2 top-0 -z-10 -translate-x-1/2 text-ink/[0.04]"
          />
          <div className="min-w-0 text-center lg:text-left">
            <span className="inline-flex items-center rounded-full border border-line/70 px-3 py-1 text-xs font-medium text-muted">
              {t("marketing.hero.badge")}
            </span>
            <TextAnimate
              as="h1"
              by="word"
              animation="blurInUp"
              duration={0.5}
              className="mt-5 max-w-3xl font-display text-display font-semibold lg:max-w-none lg:text-[clamp(3rem,1rem+4vw,4.5rem)]"
            >
              {t("marketing.hero.title")}
            </TextAnimate>
            <p className="mx-auto mt-4 max-w-xl text-lg text-muted lg:mx-0">{t("marketing.hero.subtitle")}</p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3 lg:justify-start">
              <ShimmerButton href="/login">{t("marketing.openApp")}</ShimmerButton>
              <a href="#how-it-works" className="btn-ghost">
                {t("marketing.hero.seeHowItWorks")}
              </a>
            </div>
          </div>
          <div className="flex min-w-0 justify-center lg:justify-end">
            <AnswerCard />
          </div>
        </div>
      </section>

      {/* Features: what it does, in a grid of numbered cells with a picture under each */}
      <section id="features" className="band-dark scroll-mt-24">
        <div className="mx-auto max-w-7xl px-6 py-24 md:py-32">
          <h2 className="flex items-start gap-3 font-display text-[clamp(4rem,2rem+9vw,9rem)] font-light leading-[0.95]">
            {t("marketing.features.title")}
            <ScanEye aria-hidden="true" className="mt-[0.35em] size-[0.28em] shrink-0 text-primary-ink" />
          </h2>
          <div className="mt-16 md:mt-20">
            <FeatureShowcase />
          </div>
        </div>
      </section>

      {/* How it works: the five stages of a consultation, told while you scroll */}
      <section id="how-it-works" className="scroll-mt-24">
        <div className="mx-auto max-w-7xl px-6 py-24 md:py-32">
          <span className="eyebrow text-primary-ink">{t("marketing.howItWorks.eyebrow")}</span>
          <h2 className="mt-3 max-w-4xl font-display text-[clamp(2.25rem,1.5rem+3vw,4rem)] font-light leading-[1.05]">
            {t("marketing.howItWorks.title")}
          </h2>
          <p className="mt-6 max-w-2xl text-lg text-muted">{t("marketing.howItWorks.body")}</p>
          <div className="mt-12 md:mt-16">
            <HowItWorksStory />
          </div>
        </div>
      </section>

      {/* Safeguards: three checks before an answer reaches you, each one you can try */}
      <section id="safeguards" className="band-dark scroll-mt-24 overflow-hidden">
        <div className="mx-auto max-w-7xl px-6 py-24 md:py-32">
          <h2 className="max-w-4xl font-display text-[clamp(2.25rem,1.5rem+3vw,4rem)] font-light leading-[1.05]">
            {t("marketing.safeguards.title")}
          </h2>
          <p className="mb-12 mt-6 max-w-2xl text-lg text-muted">{t("marketing.safeguards.subtitle")}</p>
          <TrustCarousel />
        </div>
      </section>

      {/* Agents and platform: one row to choose from, one panel that says what it is */}
      <section id="agents" className="scroll-mt-24">
        <div className="mx-auto max-w-7xl px-6 py-24 md:py-32">
          <h2 className="max-w-4xl font-display text-[clamp(2.25rem,1.5rem+3vw,4rem)] font-light leading-[1.05]">
            {t("marketing.chapters.title")}
          </h2>
          <p className="mb-12 mt-6 max-w-2xl text-lg text-muted">{t("marketing.chapters.subtitle")}</p>
          <ChapterStrip />
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="scroll-mt-24 border-t border-line/60">
        <div className="mx-auto max-w-3xl px-6 py-24">
          <h2 className="font-display text-title font-semibold">{t("marketing.faq.title")}</h2>
          <div className="mt-6 space-y-3">
            {FAQS.map((f) => (
              <details
                key={f.qKey}
                className="card group transition-colors duration-200 open:bg-primary-soft/40"
              >
                <summary className="cursor-pointer list-none font-semibold [&::-webkit-details-marker]:hidden">
                  <span className="flex items-center justify-between transition-colors duration-200 group-hover:text-primary">
                    {t(f.qKey)}
                    <span className="transition-transform duration-300 ease-ios group-open:rotate-90 group-open:text-primary">
                      ›
                    </span>
                  </span>
                </summary>
                <p className="mt-2 text-sm text-muted">{t(f.aKey)}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="band-dark">
        <div className="mx-auto max-w-3xl px-6 py-24 text-center">
          <h2 className="font-display text-display font-semibold">{t("marketing.cta.title")}</h2>
          <p className="mt-3 text-muted">{t("marketing.cta.subtitle")}</p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <ShimmerButton href="/login">{t("marketing.openApp")}</ShimmerButton>
            <Link href="/portal/claim" className="btn-ghost">
              {t("marketing.footer.patientPortalSetup")}
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
