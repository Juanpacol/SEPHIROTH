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
import {
  Layers,
  Link as LinkIcon,
  ShieldCheck,
  ScanEye,
  FlaskConical,
  Pill,
  BookOpen,
  Users,
} from "lucide-react";
import WingMark from "@/components/brand/wing-mark";
import AuthRedirectGate from "@/components/landing/auth-redirect-gate";
import ConsultationWalkthrough from "@/components/landing/consultation-walkthrough";
import ClaimVerifier from "@/components/landing/claim-verifier";
import CitationGuardToggle from "@/components/landing/citation-guard-toggle";
import AbstentionGate from "@/components/landing/abstention-gate";
import ProductWall from "@/components/landing/product-wall";
import { Marquee } from "@/components/magicui/marquee";
import { BentoGrid, BentoCard } from "@/components/magicui/bento-grid";
import { BorderBeam } from "@/components/magicui/border-beam";
import { TextAnimate } from "@/components/magicui/text-animate";
import { ShimmerButton } from "@/components/magicui/shimmer-button";
import { useLanguage } from "@/lib/language";

const PAIN_POINTS = [
  { icon: Layers, problemKey: "marketing.painPoints.lookups.problem", solutionKey: "marketing.painPoints.lookups.solution" },
  { icon: LinkIcon, problemKey: "marketing.painPoints.trust.problem", solutionKey: "marketing.painPoints.trust.solution" },
  { icon: ShieldCheck, problemKey: "marketing.painPoints.confidence.problem", solutionKey: "marketing.painPoints.confidence.solution" },
];

const AGENTS = [
  {
    nameKey: "marketing.agentName.coordinator",
    Icon: Users,
    bodyKey: "marketing.agentsSection.coordinator.body",
    className: "col-span-3 md:col-span-2 md:row-span-2",
  },
  {
    nameKey: "marketing.agentName.radiology",
    Icon: ScanEye,
    bodyKey: "marketing.agentsSection.radiology.body",
    className: "col-span-3 md:col-span-1",
  },
  {
    nameKey: "marketing.agentName.laboratory",
    Icon: FlaskConical,
    bodyKey: "marketing.agentsSection.laboratory.body",
    className: "col-span-3 md:col-span-1",
  },
  {
    nameKey: "marketing.agentName.drugSafety",
    Icon: Pill,
    bodyKey: "marketing.agentsSection.drugSafety.body",
    className: "col-span-3 md:col-span-1",
  },
  {
    nameKey: "marketing.agentName.evidence",
    Icon: BookOpen,
    bodyKey: "marketing.agentsSection.evidence.body",
    className: "col-span-3 md:col-span-1",
  },
];

// The real sources RAGPipeline's seeded corpus draws from (data/rag/__init__.py) —
// not decorative logos, the actual organizations behind the evidence. Org
// names/acronyms are proper nouns and stay unlocalized.
const SOURCES = [
  "American Diabetes Association",
  "ACC / AHA",
  "GOLD",
  "KDIGO",
  "USPSTF",
  "PubMed / NCBI",
];

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

      {/* Hero */}
      <section className="relative mx-auto max-w-6xl overflow-hidden px-6 py-24 text-center md:py-32">
        <WingMark
          size={420}
          className="pointer-events-none absolute left-1/2 top-0 -z-10 -translate-x-1/2 text-ink/[0.04]"
        />
        <span className="inline-flex items-center rounded-full border border-line/70 px-3 py-1 text-xs font-medium text-muted">
          {t("marketing.hero.badge")}
        </span>
        <TextAnimate
          as="h1"
          by="word"
          animation="blurInUp"
          duration={0.5}
          className="mx-auto mt-5 max-w-2xl text-3xl font-extrabold tracking-tight md:text-5xl"
        >
          {t("marketing.hero.title")}
        </TextAnimate>
        <p className="mx-auto mt-4 max-w-xl text-lg text-muted">{t("marketing.hero.subtitle")}</p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <ShimmerButton href="/login">{t("marketing.openApp")}</ShimmerButton>
          <a href="#how-it-works" className="btn-ghost">
            {t("marketing.hero.seeHowItWorks")}
          </a>
        </div>

        <div className="relative mx-auto mt-16 max-w-2xl rounded-squircle text-left">
          <BorderBeam size={90} duration={8} colorFrom="#3683F8" colorTo="#8C92AC" />
          <ConsultationWalkthrough />
        </div>
      </section>

      {/* Evidence sources — real orgs the RAG corpus cites, not logos */}
      <section className="border-y border-line/60 bg-primary-soft/20 py-6">
        <Marquee pauseOnHover className="[--duration:32s]">
          {SOURCES.map((s) => (
            <span key={s} className="mx-2 whitespace-nowrap text-sm font-semibold text-muted">
              {s}
            </span>
          ))}
        </Marquee>
      </section>

      {/* Pain points — what actually costs a clinician time and trust, and how SEPHIROTH answers it */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <h2 className="text-center text-2xl font-extrabold md:text-3xl">{t("marketing.painPoints.title")}</h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-muted">{t("marketing.painPoints.subtitle")}</p>
        <div className="mt-10 space-y-5">
          {PAIN_POINTS.map((v) => (
            <div key={v.problemKey} className="card grid gap-4 md:grid-cols-[auto_1fr_1fr] md:items-center">
              <div className="inline-flex rounded-2xl bg-primary-soft p-2.5 text-primary md:self-start">
                <v.icon size={20} />
              </div>
              <div>
                <span className="text-xs font-bold uppercase tracking-wide text-danger">
                  {t("marketing.painPoints.problemLabel")}
                </span>
                <p className="mt-1 text-sm text-muted">{t(v.problemKey)}</p>
              </div>
              <div className="border-t border-line/60 pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0">
                <span className="text-xs font-bold uppercase tracking-wide text-primary">
                  {t("marketing.painPoints.solutionLabel")}
                </span>
                <p className="mt-1 text-sm">{t(v.solutionKey)}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Product wall — real screenshots, not stock photos */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <h2 className="text-center text-2xl font-extrabold md:text-3xl">{t("marketing.productSection.title")}</h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-muted">{t("marketing.productSection.subtitle")}</p>
        <div className="mt-8">
          <ProductWall />
        </div>
      </section>

      {/* How it works — the mechanics, for the reader who wants to know before trusting it */}
      <section id="how-it-works" className="scroll-mt-24 border-t border-line/60 bg-primary-soft/30">
        <div className="mx-auto max-w-4xl px-6 py-24">
          <span className="text-xs font-bold uppercase tracking-wide text-primary">
            {t("marketing.howItWorks.eyebrow")}
          </span>
          <h2 className="mt-2 text-2xl font-extrabold md:text-3xl">{t("marketing.howItWorks.title")}</h2>
          <p className="mt-3 max-w-2xl text-muted">
            {t("marketing.howItWorks.bodyPre")}{" "}
            <span className="font-semibold text-primary">{t("marketing.walkthrough.runIt")}</span>{" "}
            {t("marketing.howItWorks.bodyPost")}
          </p>
        </div>
      </section>

      {/* Safeguards */}
      <section id="safeguards" className="scroll-mt-24 mx-auto max-w-6xl px-6 py-24">
        <h2 className="text-2xl font-extrabold md:text-3xl">{t("marketing.safeguards.title")}</h2>
        <p className="mt-3 max-w-2xl text-muted">{t("marketing.safeguards.subtitle")}</p>
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 font-bold">{t("marketing.safeguards.claimVerifierTitle")}</h3>
            <p className="mb-3 text-sm text-muted">{t("marketing.safeguards.claimVerifierBody")}</p>
            <ClaimVerifier />
          </div>
          <div>
            <h3 className="mb-2 font-bold">{t("marketing.safeguards.citationGuardTitle")}</h3>
            <p className="mb-3 text-sm text-muted">{t("marketing.safeguards.citationGuardBody")}</p>
            <CitationGuardToggle />
            <h3 className="mb-2 mt-8 font-bold">{t("marketing.safeguards.abstentionGateTitle")}</h3>
            <p className="mb-3 text-sm text-muted">{t("marketing.safeguards.abstentionGateBody")}</p>
            <AbstentionGate />
          </div>
        </div>
      </section>

      {/* Agents */}
      <section id="agents" className="scroll-mt-24 border-t border-line/60 bg-primary-soft/30">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <h2 className="text-2xl font-extrabold md:text-3xl">{t("marketing.agentsSection.title")}</h2>
          <p className="mt-3 max-w-2xl text-muted">{t("marketing.agentsSection.subtitle")}</p>
          <BentoGrid className="mt-8 auto-rows-[14rem] md:grid-cols-4">
            {AGENTS.map((a) => (
              <BentoCard
                key={a.nameKey}
                name={t(a.nameKey)}
                Icon={a.Icon}
                description={t(a.bodyKey)}
                className={a.className}
              />
            ))}
          </BentoGrid>
        </div>
      </section>

      {/* Trace showcase */}
      <section className="mx-auto max-w-4xl px-6 py-24">
        <h2 className="text-2xl font-extrabold md:text-3xl">{t("marketing.trace.title")}</h2>
        <p className="mt-3 max-w-2xl text-muted">{t("marketing.trace.body")}</p>
        <div className="card card-interactive mt-8 border-l-4 border-primary/40">
          <ol className="space-y-3 text-sm">
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary" /> {t("marketing.trace.step1")}
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary" /> {t("marketing.trace.step2Pre")}{" "}
              <code className="rounded bg-surface px-1">search_clinical_guidelines</code>
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary" /> {t("marketing.trace.step3")}
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-danger" /> {t("marketing.trace.step4")}
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-success" /> {t("marketing.trace.step5")}
            </li>
          </ol>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="scroll-mt-24 border-t border-line/60">
        <div className="mx-auto max-w-3xl px-6 py-24">
          <h2 className="text-2xl font-extrabold md:text-3xl">{t("marketing.faq.title")}</h2>
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
      <section className="mx-auto max-w-3xl px-6 py-24 text-center">
        <h2 className="text-2xl font-extrabold md:text-3xl">{t("marketing.cta.title")}</h2>
        <p className="mt-3 text-muted">{t("marketing.cta.subtitle")}</p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <ShimmerButton href="/login">{t("marketing.openApp")}</ShimmerButton>
          <Link href="/portal/claim" className="btn-ghost">
            {t("marketing.footer.patientPortalSetup")}
          </Link>
        </div>
      </section>
    </>
  );
}
