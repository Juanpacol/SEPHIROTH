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
import AuthRedirectGate from "@/components/landing/auth-redirect-gate";
import ScrollEffects from "@/components/landing/scroll-effects";
import FeatureShowcase from "@/components/landing/feature-showcase";
import AccentTitle from "@/components/landing/accent-title";
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
          <h2 className="flex items-start gap-3 font-display text-[clamp(4rem,2rem+9vw,9rem)] font-light leading-[0.95]">
            {t("marketing.features.title")}
            <ScanEye aria-hidden="true" className="mt-[0.35em] size-[0.28em] shrink-0 text-primary-ink" />
          </h2>
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
          <p className="mt-6 max-w-2xl text-lg text-muted">{t("marketing.howItWorks.body")}</p>
          <div className="mt-12 md:mt-16">
            <AnswerAnatomy />
          </div>
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
      <section className="border-t border-line/60">
        <div className="mx-auto max-w-3xl px-6 py-24 text-center">
          <h2 className="font-display text-display font-semibold">{t("marketing.cta.title")}</h2>
          <p className="mt-3 text-muted">{t("marketing.cta.subtitle")}</p>
          <p className="mx-auto mt-4 max-w-2xl text-sm text-muted">{t("marketing.cta.around")}</p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <CtaButton href="/login">{t("marketing.openApp")}</CtaButton>
            <Link href="/portal/claim" className="btn-ghost">
              {t("marketing.footer.patientPortalSetup")}
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
