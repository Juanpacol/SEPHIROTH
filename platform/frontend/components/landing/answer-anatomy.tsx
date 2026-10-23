"use client";

/** "How it works" as one sample answer taken apart. The answer is shown as the product shows it, and
 * beside it the five things that happened to it, in order. Point at, focus or tap a step and the part
 * of the answer it is about lights up and the rest quiets; point at a part and its step lights up.
 *
 * Nothing moves by itself and nothing is hidden behind a hover: all five steps are always written out,
 * and the same highlight follows the keyboard focus, so a touch screen and a keyboard get the whole
 * explanation too. */

import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import FeatureMediaView from "./feature-media";
import { ANATOMY_STEPS, type AnatomyStepId } from "@/lib/landing-anatomy";
import { useLanguage } from "@/lib/language";

/** The picture behind the glass: the Ask cell's, a scan with a web of lines over it. */
const BACKDROP = {
  kind: "image",
  src: "/landing/features/ask-spine.webp",
  altKey: "marketing.features.ask.alt",
} as const;

/** A part of the answer that belongs to a step: lit when its step is the current one. */
function Part({
  step,
  active,
  onActivate,
  className = "",
  children,
}: {
  step: AnatomyStepId;
  active: AnatomyStepId;
  onActivate: (id: AnatomyStepId) => void;
  className?: string;
  children: React.ReactNode;
}) {
  const on = step === active;
  return (
    <span
      data-part={step}
      data-active={on}
      onMouseEnter={() => onActivate(step)}
      className={`rounded-lg transition-[opacity,background-color,box-shadow] duration-slow ease-standard ${
        on
          ? "bg-[#3683F8]/20 opacity-100 shadow-[0_0_0_1px_rgb(120_165_250/0.55),0_0_32px_rgb(54_131_248/0.35)]"
          : "opacity-45"
      } ${className}`}
    >
      {children}
    </span>
  );
}

export default function AnswerAnatomy() {
  const { t } = useLanguage();
  const [active, setActive] = useState<AnatomyStepId>("route");

  return (
    <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-16">
      {/* The answer, as the product shows it. */}
      <div
        data-anatomy-card
        onPointerMove={(e) => {
          // A soft light under the pointer, for devices that have one.
          if (e.pointerType !== "mouse") return;
          const box = e.currentTarget.getBoundingClientRect();
          e.currentTarget.style.setProperty("--mx", `${e.clientX - box.left}px`);
          e.currentTarget.style.setProperty("--my", `${e.clientY - box.top}px`);
        }}
        className="group/card relative overflow-hidden rounded-[28px] border border-white/15 shadow-raised-lg"
      >
        {/* One of the feature grid's pictures, in the same blue, behind the glass. */}
        <div aria-hidden="true" className="absolute inset-0">
          <FeatureMediaView media={BACKDROP} />
        </div>
        <div
          aria-hidden="true"
          data-spotlight
          className="pointer-events-none absolute inset-0 z-10 opacity-0 transition-opacity duration-[600ms] ease-standard group-hover/card:opacity-100"
          style={{
            background:
              "radial-gradient(420px circle at var(--mx, 50%) var(--my, 50%), rgb(120 165 250 / 0.18), transparent 70%)",
          }}
        />
        <div className="relative bg-surface/70 p-6 backdrop-blur-md md:p-8">
          <div className="eyebrow text-white/70">{t("marketing.anatomy.card.label")}</div>

          <p className="mt-4 text-sm leading-relaxed">
            <Part step="route" active={active} onActivate={setActive} className="inline-block px-2 py-1">
              <span className="mr-2 inline-flex rounded-full bg-surface px-2.5 py-0.5 text-xs font-semibold text-primary-ink">
                {t("marketing.agentName.evidence")}
              </span>
              <span className="font-medium">{t("marketing.sample.question")}</span>
            </Part>
          </p>

          <div className="mt-6 space-y-4 text-[15px] leading-relaxed md:text-base">
            <p>
              <Part step="write" active={active} onActivate={setActive} className="px-1.5 py-0.5">
                {t("marketing.anatomy.card.answer")}
              </Part>{" "}
              <Part
                step="guard"
                active={active}
                onActivate={setActive}
                className="inline-flex flex-wrap items-center gap-x-2 px-1.5 py-0.5 font-mono text-[11px] uppercase tracking-[0.12em]"
              >
                <span className="text-primary-ink">[{t("marketing.anatomy.card.cite1")}]</span>
                <span className="text-danger line-through opacity-80">
                  [{t("marketing.anatomy.card.cite2")}]
                </span>
                <span className="font-semibold text-danger">{t("marketing.anatomy.card.removed")}</span>
              </Part>
            </p>

            <p>
              <Part step="verify" active={active} onActivate={setActive} className="block px-1.5 py-1">
                <span className="text-muted line-through">{t("marketing.claim2.text")}</span>{" "}
                <span className="ml-1 inline-flex items-center gap-1 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-danger">
                  <ShieldCheck size={13} aria-hidden="true" />
                  {t("marketing.anatomy.card.excluded")}
                </span>
              </Part>
            </p>

            <p>
              <Part step="abstain" active={active} onActivate={setActive} className="block px-1.5 py-1">
                <span className="font-medium">{t("marketing.anatomy.card.abstain")}</span>
              </Part>
            </p>
          </div>
        </div>
      </div>

      {/* The five things that happened to it. */}
      <ol aria-label={t("marketing.anatomy.stepsLabel")} className="space-y-1">
        {ANATOMY_STEPS.map((step, i) => {
          const on = step.id === active;
          return (
            <li key={step.id}>
              <button
                type="button"
                data-step={step.id}
                data-active={on}
                aria-pressed={on}
                onMouseEnter={() => setActive(step.id)}
                onFocus={() => setActive(step.id)}
                onClick={() => setActive(step.id)}
                className="tap group relative grid w-full grid-cols-[4.25rem_1fr] items-start gap-3 border-l border-white/15 px-4 py-4 text-left transition-colors duration-normal ease-standard hover:border-white/40 data-[active=true]:border-[#b6cfff]"
              >
                <span className="font-display text-5xl font-light leading-none text-white/35 transition-colors duration-slow ease-standard group-data-[active=true]:text-[#b6cfff]">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span>
                  <span className="nav-underline block w-fit py-1 font-display text-2xl font-light uppercase leading-tight tracking-wide group-data-[active=true]:text-white md:text-3xl [&::after]:left-0 [&::after]:right-0 [&::after]:bottom-0 group-data-[active=true]:[&::after]:scale-x-100">
                    {t(step.titleKey)}
                  </span>
                  <span className="mt-2 block text-sm leading-relaxed text-muted group-data-[active=true]:text-ink/90">
                    {t(step.bodyKey)}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
