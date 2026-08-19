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

const PAIN_POINTS = [
  {
    icon: Layers,
    problem: "A drug interaction check here, a guideline search there, a lab flag in another tab — 15+ minutes gone before you've even started reasoning about the case.",
    solution: "One question fans out to radiology, labs, drug safety, and evidence agents in parallel, and comes back synthesized — the four lookups collapse into the time it takes to read one answer.",
  },
  {
    icon: LinkIcon,
    problem: "Most clinical AI hands you a confident paragraph with no way to check where any of it came from — you either trust it blindly or re-verify it yourself, which defeats the point.",
    solution: "Every sentence is checked against what the tools actually retrieved and labeled supported, contradicted, or unverified before it ever reaches you — a cited answer, not a leap of faith.",
  },
  {
    icon: ShieldCheck,
    problem: "A wrong guess costs more than a slow one, but most tools answer with the same confidence whether the evidence is there or not.",
    solution: "Below its confidence threshold, SEPHIROTH hands back a caveat or declines outright instead of guessing — the tool tells you when to keep digging, instead of pretending it knows.",
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

      {/* Pain points — what actually costs a clinician time and trust, and how SEPHIROTH answers it */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <h2 className="text-center text-2xl font-extrabold md:text-3xl">
          Built around what actually slows you down
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-center text-muted">
          Not another chatbot bolted onto a chart — three problems that cost real minutes and real
          trust, and what we built specifically to close each one.
        </p>
        <div className="mt-10 space-y-5">
          {PAIN_POINTS.map((v) => (
            <div key={v.problem} className="card grid gap-4 md:grid-cols-[auto_1fr_1fr] md:items-center">
              <div className="inline-flex rounded-2xl bg-primary-soft p-2.5 text-primary md:self-start">
                <v.icon size={20} />
              </div>
              <div>
                <span className="text-xs font-bold uppercase tracking-wide text-danger">The problem</span>
                <p className="mt-1 text-sm text-muted">{v.problem}</p>
              </div>
              <div className="border-t border-line/60 pt-4 md:border-l md:border-t-0 md:pl-6 md:pt-0">
                <span className="text-xs font-bold uppercase tracking-wide text-primary">
                  How SEPHIROTH answers it
                </span>
                <p className="mt-1 text-sm">{v.solution}</p>
              </div>
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

      {/* How it works — the mechanics, for the reader who wants to know before trusting it */}
      <section id="how-it-works" className="scroll-mt-24 border-t border-line/60 bg-primary-soft/30">
        <div className="mx-auto max-w-4xl px-6 py-24">
          <span className="text-xs font-bold uppercase tracking-wide text-primary">
            For the curious: how it actually runs
          </span>
          <h2 className="mt-2 text-2xl font-extrabold md:text-3xl">
            The same workup you&apos;d do by hand, minus the serial part
          </h2>
          <p className="mt-3 max-w-2xl text-muted">
            Six steps, in order, every time: routing → specialists → coordinator → citation guard →
            verification → abstention — the chart review and cross-checking you already do,
            just run in parallel instead of one lookup at a time. Step through the tabs above, or
            press <span className="font-semibold text-primary">Run it</span> and watch the whole
            pipeline fire in sequence.
          </p>
        </div>
      </section>

      {/* Safeguards */}
      <section id="safeguards" className="scroll-mt-24 mx-auto max-w-6xl px-6 py-24">
        <h2 className="text-2xl font-extrabold md:text-3xl">Recommendations you can put your name behind</h2>
        <p className="mt-3 max-w-2xl text-muted">
          Three checks stand between a raw model output and anything you actually see — try each
          one yourself below.
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
          <h2 className="text-2xl font-extrabold md:text-3xl">Every specialist a case needs, none it doesn't</h2>
          <p className="mt-3 max-w-2xl text-muted">
            No fixed checklist wasting your time — only the specialists a query actually needs get
            routed in, so a drug question never sits waiting on Radiology.
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
        <h2 className="text-2xl font-extrabold md:text-3xl">Defend any recommendation, months later</h2>
        <p className="mt-3 max-w-2xl text-muted">
          A QA review, a teaching case, a question about why you acted on something — a full
          execution trace is saved alongside every answer, so you can show exactly how it was
          reached without re-running anything or trusting your memory.
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
