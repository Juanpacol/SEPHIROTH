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
import HeroSilk from "@/components/landing/hero-silk";
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

const VALUES = [
  {
    icon: Layers,
    title: "One consult, four specialists, no tab-switching",
    body: "Radiology, laboratory, drug safety, and evidence run in parallel and report to one coordinator — the workup that used to mean four lookups now takes one query.",
  },
  {
    icon: LinkIcon,
    title: "Every claim traced to a source",
    body: "Citation Guard checks each sentence against what the tools actually returned, so you're reviewing a cited answer, not re-verifying one from scratch.",
  },
  {
    icon: ShieldCheck,
    title: "Silence is a valid answer",
    body: "No evidence, no guess. Below its confidence threshold, the system hands back a caveat or an outright decline instead of costing you time on a wrong lead.",
  },
];

const AGENTS = [
  {
    name: "Coordinator",
    Icon: Users,
    body: "Reads every specialist's output and writes the one answer a clinician sees.",
    className: "col-span-3 md:col-span-2 md:row-span-2",
  },
  {
    name: "Radiology",
    Icon: ScanEye,
    body: "Reads medical images and returns structured findings, not just prose.",
    className: "col-span-3 md:col-span-1",
  },
  {
    name: "Laboratory",
    Icon: FlaskConical,
    body: "Flags lab values against reference ranges, unit-aware.",
    className: "col-span-3 md:col-span-1",
  },
  {
    name: "Drug Safety",
    Icon: Pill,
    body: "Cross-checks a medication list for known interactions.",
    className: "col-span-3 md:col-span-1",
  },
  {
    name: "Evidence",
    Icon: BookOpen,
    body: "Pulls guidelines and PubMed results — every line cited, nothing invented.",
    className: "col-span-3 md:col-span-1",
  },
];

// The real sources RAGPipeline's seeded corpus draws from (data/rag/__init__.py) —
// not decorative logos, the actual organizations behind the evidence.
const SOURCES = [
  "American Diabetes Association",
  "ACC / AHA",
  "GOLD",
  "KDIGO",
  "USPSTF",
  "PubMed / NCBI",
];

const FAQS = [
  {
    q: "Is this a medical device?",
    a: "No. SEPHIROTH is decision support for research and education — every answer requires professional review before any clinical use.",
  },
  {
    q: "What data does it see?",
    a: "Only what a clinician puts into a consultation — patient context, notes, and the query itself. See the privacy notice in the project README for exactly what leaves the machine.",
  },
  {
    q: "What happens when it doesn't know?",
    a: "The abstention gate checks confidence and evidence support before an answer ever ships. Below its threshold, it declines instead of guessing — try the slider above.",
  },
  {
    q: "Where do citations come from?",
    a: "Retrieved clinical guidelines and PubMed results only, nowhere else. Citation Guard strips anything the model added that no tool actually returned.",
  },
  {
    q: "Can I audit a past answer?",
    a: "Yes — every consultation saves a replayable execution trace: which agents ran, what they called, and how each claim was classified.",
  },
];

export default function LandingPage() {
  return (
    <>
      <AuthRedirectGate />

      {/* Hero */}
      <section className="relative mx-auto max-w-6xl overflow-hidden px-6 py-24 text-center md:py-32">
        <HeroSilk />
        <WingMark
          size={420}
          className="pointer-events-none absolute left-1/2 top-0 -z-10 -translate-x-1/2 text-ink/[0.04]"
        />
        <span className="inline-flex items-center rounded-full border border-line/70 px-3 py-1 text-xs font-medium text-muted">
          Research &amp; education use — not a medical device
        </span>
        <TextAnimate
          as="h1"
          by="word"
          animation="blurInUp"
          duration={0.5}
          className="mx-auto mt-5 max-w-2xl text-3xl font-extrabold tracking-tight md:text-5xl"
        >
          Give every clinician back the minutes lost to lookups
        </TextAnimate>
        <p className="mx-auto mt-4 max-w-xl text-lg text-muted">
          One query fans out to radiology, labs, drug safety, and evidence agents, comes back
          cited and verified, and tells you plainly when it doesn&apos;t know — less chart-digging,
          more time with the patient.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <ShimmerButton href="/login">Open the app</ShimmerButton>
          <a href="#how-it-works" className="btn-ghost">
            See how it works
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

      {/* Values */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <div className="grid gap-5 md:grid-cols-3">
          {VALUES.map((v) => (
            <div key={v.title} className="card card-interactive group">
              <div className="mb-3 inline-flex rounded-2xl bg-primary-soft p-2.5 text-primary transition-transform duration-300 ease-ios group-hover:scale-110 group-hover:rotate-3">
                <v.icon size={20} />
              </div>
              <h3 className="font-bold">{v.title}</h3>
              <p className="mt-1.5 text-sm text-muted">{v.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Product wall — real screenshots, not stock photos */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <h2 className="text-center text-2xl font-extrabold md:text-3xl">The actual product</h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-muted">
          Every tile below is a real screenshot — the dashboard, a live consultation, cited
          evidence search, streaming vision analysis.
        </p>
        <div className="mt-8">
          <ProductWall />
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="scroll-mt-24 border-t border-line/60 bg-primary-soft/30">
        <div className="mx-auto max-w-4xl px-6 py-24">
          <h2 className="text-2xl font-extrabold md:text-3xl">The workup, compressed into one pass</h2>
          <p className="mt-3 max-w-2xl text-muted">
            Six steps, in order, every time: routing → specialists → coordinator → citation guard →
            verification → abstention — the same chart review and cross-checking a clinician would
            do by hand, run in parallel instead of serially. Step through the tabs above, or press{" "}
            <span className="font-semibold text-primary">Run it</span> and watch the whole pipeline
            fire in sequence.
          </p>
        </div>
      </section>

      {/* Safeguards */}
      <section id="safeguards" className="scroll-mt-24 mx-auto max-w-6xl px-6 py-24">
        <h2 className="text-2xl font-extrabold md:text-3xl">Safeguards, made visible</h2>
        <p className="mt-3 max-w-2xl text-muted">
          Three of the checks every answer has to clear before it reaches a clinician — try them
          yourself below.
        </p>
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 font-bold">5-state claim verifier</h3>
            <p className="mb-3 text-sm text-muted">
              Hover or tap a claim below to see how it was classified against retrieved evidence.
            </p>
            <ClaimVerifier />
          </div>
          <div>
            <h3 className="mb-2 font-bold">Citation Guard</h3>
            <p className="mb-3 text-sm text-muted">
              Toggle between the model&apos;s raw output and what actually reaches a clinician.
            </p>
            <CitationGuardToggle />
            <h3 className="mb-2 mt-8 font-bold">Abstention gate</h3>
            <p className="mb-3 text-sm text-muted">
              Drag the slider to see the system decline instead of guessing.
            </p>
            <AbstentionGate />
          </div>
        </div>
      </section>

      {/* Agents */}
      <section id="agents" className="scroll-mt-24 border-t border-line/60 bg-primary-soft/30">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <h2 className="text-2xl font-extrabold md:text-3xl">Five specialists, one coordinator</h2>
          <p className="mt-3 max-w-2xl text-muted">
            Only the specialists a query actually needs get routed in — a drug question never wakes
            up Radiology.
          </p>
          <BentoGrid className="mt-8 auto-rows-[14rem] md:grid-cols-4">
            {AGENTS.map((a) => (
              <BentoCard key={a.name} name={a.name} Icon={a.Icon} description={a.body} className={a.className} />
            ))}
          </BentoGrid>
        </div>
      </section>

      {/* Trace showcase */}
      <section className="mx-auto max-w-4xl px-6 py-24">
        <h2 className="text-2xl font-extrabold md:text-3xl">Every consultation is replayable</h2>
        <p className="mt-3 max-w-2xl text-muted">
          A full execution trace — every agent, every tool call, every verification decision — is
          saved alongside each answer, so a clinician or an auditor can see exactly how it was
          reached, months later, without re-running anything.
        </p>
        <div className="card card-interactive mt-8 border-l-4 border-primary/40">
          <ol className="space-y-3 text-sm">
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary" /> Routing selected Evidence,
              Laboratory
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary" /> Evidence called{" "}
              <code className="rounded bg-surface px-1">search_clinical_guidelines</code>
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary" /> Coordinator synthesized 2
              specialist sections
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-danger" /> Citation Guard removed 1
              fabricated citation
            </li>
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-success" /> Verification: 2 supported, 1
              contradicted, 1 unknown
            </li>
          </ol>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="scroll-mt-24 border-t border-line/60">
        <div className="mx-auto max-w-3xl px-6 py-24">
          <h2 className="text-2xl font-extrabold md:text-3xl">Frequently asked</h2>
          <div className="mt-6 space-y-3">
            {FAQS.map((f) => (
              <details
                key={f.q}
                className="card group transition-colors duration-200 open:bg-primary-soft/40"
              >
                <summary className="cursor-pointer list-none font-semibold [&::-webkit-details-marker]:hidden">
                  <span className="flex items-center justify-between transition-colors duration-200 group-hover:text-primary">
                    {f.q}
                    <span className="transition-transform duration-300 ease-ios group-open:rotate-90 group-open:text-primary">
                      ›
                    </span>
                  </span>
                </summary>
                <p className="mt-2 text-sm text-muted">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Closing CTA */}
      <section className="mx-auto max-w-3xl px-6 py-24 text-center">
        <h2 className="text-2xl font-extrabold md:text-3xl">Get an hour of chart review back today</h2>
        <p className="mt-3 text-muted">
          Sign in as a clinician to run a consultation, or set up your portal account with a claim
          code from your care team.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <ShimmerButton href="/login">Open the app</ShimmerButton>
          <Link href="/portal/claim" className="btn-ghost">
            Patient portal setup
          </Link>
        </div>
      </section>
    </>
  );
}
