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

import AuthRedirectGate from "@/components/landing/auth-redirect-gate";
import ScrollEffects from "@/components/landing/scroll-effects";
import FeatureShowcase from "@/components/landing/feature-showcase";
import AccentTitle from "@/components/landing/accent-title";
import Reveal from "@/components/landing/reveal";
import AnswerAnatomy from "@/components/landing/answer-anatomy";
import CtaButton from "@/components/landing/cta-button";
import HeroTriptych from "@/components/landing/hero-triptych";
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

      {/* Hero: three full-height panels with the headline across them */}
      <HeroTriptych />

      {/* Features: what it does, in a grid of numbered cells with a picture under each */}
      <section id="features" className="scroll-mt-24 border-t border-line/60">
        <div className="mx-auto max-w-7xl px-6 py-24 md:py-32">
          <AccentTitle
            text={t("marketing.features.title")}
            accentWords={1}
            className="text-[clamp(4rem,2rem+9vw,9rem)]"
          />
          <div className="mt-16 md:mt-20">
            <FeatureShowcase />
          </div>
        </div>
      </section>

      {/* How it works: one answer taken apart, each step pinned to the part it is about */}
      <section id="how-it-works" className="scroll-mt-24 border-t border-line/60">
        <div className="mx-auto max-w-7xl px-6 py-24 md:py-32">
          <span className="eyebrow text-primary-ink">{t("marketing.howItWorks.eyebrow")}</span>
          <AccentTitle
            text={t("marketing.howItWorks.title")}
            className="mt-3 max-w-5xl text-[clamp(3rem,1rem+6vw,7rem)]"
          />
          <Reveal as="p" className="mt-6 max-w-2xl text-lg text-muted">
            {t("marketing.howItWorks.body")}
          </Reveal>
          <Reveal className="mt-12 md:mt-16" delay={120}>
            <AnswerAnatomy />
          </Reveal>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="scroll-mt-24 border-t border-line/60">
        <div className="mx-auto max-w-4xl px-6 py-24 md:py-32">
          <AccentTitle text={t("marketing.faq.title")} className="text-[clamp(3rem,1rem+6vw,6.5rem)]" />
          <Reveal className="mt-12 border-t border-white/15" delay={100}>
            {FAQS.map((f) => (
              <details key={f.qKey} className="group border-b border-white/15">
                <summary className="tap flex cursor-pointer list-none items-center justify-between gap-6 py-6 [&::-webkit-details-marker]:hidden">
                  <span className="nav-underline w-fit py-1 font-display text-2xl font-light uppercase tracking-wide transition-colors duration-normal ease-standard group-open:text-[#b6cfff] md:text-3xl [&::after]:left-0 [&::after]:right-0 [&::after]:bottom-0">
                    {t(f.qKey)}
                  </span>
                  <span
                    aria-hidden="true"
                    className="font-display text-4xl font-light leading-none text-white/50 transition-transform duration-300 ease-ios group-open:rotate-45 group-open:text-[#b6cfff]"
                  >
                    +
                  </span>
                </summary>
                <p className="max-w-2xl pb-6 text-base leading-relaxed text-muted">{t(f.aKey)}</p>
              </details>
            ))}
          </Reveal>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="border-t border-line/60">
        <div className="mx-auto max-w-4xl px-6 py-24 text-center md:py-32">
          <AccentTitle
            text={t("marketing.cta.title")}
            accentWords={3}
            className="text-[clamp(2.75rem,1rem+5.5vw,6rem)]"
          />
          <Reveal delay={150}>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-muted">{t("marketing.cta.subtitle")}</p>
            <p className="mx-auto mt-4 max-w-2xl text-sm text-muted">{t("marketing.cta.around")}</p>
          </Reveal>
          <Reveal className="mt-8 flex flex-wrap items-center justify-center gap-3" delay={280}>
            <CtaButton href="/login">{t("marketing.openApp")}</CtaButton>
            <CtaButton href="/portal/claim" variant="line">
              {t("marketing.footer.patientPortalSetup")}
            </CtaButton>
          </Reveal>
        </div>
      </section>
    </>
  );
}
