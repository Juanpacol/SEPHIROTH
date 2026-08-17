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
} from "lucide-react";
import WingMark from "@/components/brand/wing-mark";
import AgentBadge from "@/components/agent-badge";
import AuthRedirectGate from "@/components/landing/auth-redirect-gate";
import ConsultationWalkthrough from "@/components/landing/consultation-walkthrough";
import ClaimVerifier from "@/components/landing/claim-verifier";
import CitationGuardToggle from "@/components/landing/citation-guard-toggle";
import AbstentionGate from "@/components/landing/abstention-gate";

const VALUES = [
  {
    icon: Layers,
    title: "Specialists, not one generalist",
    body: "Radiology, laboratory, drug safety, and evidence agents each reason within their own domain, then a coordinator synthesizes what they found.",
  },
  {
    icon: LinkIcon,
    title: "Every claim traced to a source",
    body: "Citations are checked against what the tools actually returned. Anything that can't be traced back gets stripped, not guessed at.",
  },
  {
    icon: ShieldCheck,
    title: "Silence is a valid answer",
    body: "When the evidence isn't there, the system says so — a caveat banner or an outright decline, never a confident-sounding guess.",
  },
];

const AGENTS = [
  { name: "Radiology", body: "Analyzes medical images and structured findings." },
  { name: "Laboratory", body: "Interprets lab values against reference ranges." },
  { name: "Drug Safety", body: "Screens medication lists for interactions." },
  { name: "Evidence", body: "Retrieves guidelines and PubMed results, always cited." },
  { name: "Coordinator", body: "Synthesizes every specialist's findings into one answer." },
];

const FAQS = [
  {
    q: "Is this a medical device?",
    a: "No. SEPHIROTH is decision support for research and education — every answer requires professional review before any clinical use.",
  },
  {
    q: "What data does it see?",
    a: "Whatever a clinician includes in a consultation — patient context, notes, and query text. See the privacy notice in the project README for what leaves the machine.",
  },
  {
    q: "What happens when it doesn't know?",
    a: "The abstention gate checks confidence and evidence support before answering. Below its threshold, it declines rather than guesses — see the demo above.",
  },
  {
    q: "Where do citations come from?",
    a: "Retrieved clinical guidelines and PubMed results only. Citation Guard strips anything the model added that wasn't actually returned by a tool.",
  },
  {
    q: "Can I audit a past answer?",
    a: "Every consultation builds a replayable execution trace — which agents ran, what they called, and how the verification pass classified each claim.",
  },
];

export default function LandingPage() {
  return (
    <>
      <AuthRedirectGate />

      {/* Hero */}
      <section className="relative mx-auto max-w-6xl px-6 py-24 text-center md:py-32">
        <WingMark
          size={420}
          className="pointer-events-none absolute left-1/2 top-0 -z-10 -translate-x-1/2 text-ink/[0.04]"
        />
        <span className="inline-flex items-center rounded-full border border-line/70 px-3 py-1 text-xs font-medium text-muted">
          Research &amp; education use — not a medical device
        </span>
        <h1 className="mx-auto mt-5 max-w-2xl text-3xl font-extrabold tracking-tight md:text-5xl">
          Clinical decisions, with the reasoning shown
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-lg text-muted">
          Multi-agent AI that reads the patient record, retrieves the evidence, cites every claim,
          and declines when the evidence isn&apos;t there.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link href="/login" className="btn-primary">
            Open the app
          </Link>
          <a href="#how-it-works" className="btn-ghost">
            See how it works
          </a>
        </div>

        <div className="mx-auto mt-16 max-w-2xl text-left">
          <ConsultationWalkthrough />
        </div>
      </section>

      {/* Values */}
      <section className="mx-auto max-w-6xl px-6 py-24">
        <div className="grid gap-5 md:grid-cols-3">
          {VALUES.map((v) => (
            <div key={v.title} className="card">
              <div className="mb-3 inline-flex rounded-2xl bg-primary-soft p-2.5 text-primary">
                <v.icon size={20} />
              </div>
              <h3 className="font-bold">{v.title}</h3>
              <p className="mt-1.5 text-sm text-muted">{v.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="scroll-mt-24 border-t border-line/60 bg-primary-soft/30">
        <div className="mx-auto max-w-4xl px-6 py-24">
          <h2 className="text-2xl font-extrabold md:text-3xl">How a consultation actually runs</h2>
          <p className="mt-3 max-w-2xl text-muted">
            Routing → specialists → coordinator → citation guard → verification → abstention. Step
            through it above, or press{" "}
            <span className="font-semibold text-primary">Run it</span> to watch it play out.
          </p>
        </div>
      </section>

      {/* Safeguards */}
      <section id="safeguards" className="scroll-mt-24 mx-auto max-w-6xl px-6 py-24">
        <h2 className="text-2xl font-extrabold md:text-3xl">Safeguards, made visible</h2>
        <p className="mt-3 max-w-2xl text-muted">
          Two of the checks every answer passes through before it reaches a clinician.
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
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {AGENTS.map((a) => (
              <div key={a.name} className="card">
                <AgentBadge name={a.name} />
                <p className="mt-2 text-sm text-muted">{a.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trace showcase */}
      <section className="mx-auto max-w-4xl px-6 py-24">
        <h2 className="text-2xl font-extrabold md:text-3xl">Every consultation is replayable</h2>
        <p className="mt-3 max-w-2xl text-muted">
          A full execution trace — every agent, every tool call, every verification decision — is
          saved alongside each answer, so a clinician (or an auditor) can see exactly how it was
          reached.
        </p>
        <div className="card mt-8 border-l-4 border-primary/40">
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
              <details key={f.q} className="card group">
                <summary className="cursor-pointer list-none font-semibold [&::-webkit-details-marker]:hidden">
                  <span className="flex items-center justify-between">
                    {f.q}
                    <span className="transition-transform group-open:rotate-90">›</span>
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
        <h2 className="text-2xl font-extrabold md:text-3xl">Ready to see it on your own cases?</h2>
        <p className="mt-3 text-muted">
          Sign in as a clinician, or set up your portal account with a claim code.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link href="/login" className="btn-primary">
            Open the app
          </Link>
          <Link href="/portal/claim" className="btn-ghost">
            Patient portal setup
          </Link>
        </div>
      </section>
    </>
  );
}
