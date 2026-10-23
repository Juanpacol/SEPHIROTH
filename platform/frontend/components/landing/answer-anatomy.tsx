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
import { ANATOMY_STEPS, type AnatomyStepId } from "@/lib/landing-anatomy";
import { useLanguage } from "@/lib/language";

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
        on ? "bg-primary-soft opacity-100 shadow-[0_0_0_4px_rgb(var(--color-primary-soft))]" : "opacity-55"
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
        className="band-dark rounded-[28px] border border-line/60 p-6 shadow-raised-lg md:p-8"
      >
        <div className="eyebrow text-muted">{t("marketing.anatomy.card.label")}</div>

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
              className="inline-flex flex-wrap items-center gap-x-2 px-1.5 py-0.5 font-mono text-xs"
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
              <span className="ml-1 inline-flex items-center gap-1 text-xs font-semibold text-danger">
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
                className="tap group grid w-full grid-cols-[2.25rem_1fr] gap-3 rounded-2xl px-3 py-3 text-left transition-colors duration-normal ease-standard hover:bg-primary-soft/60 data-[active=true]:bg-primary-soft"
              >
                <span className="eyebrow pt-1 text-primary-ink">{String(i + 1).padStart(2, "0")}</span>
                <span>
                  <span className="block font-display text-2xl font-light leading-tight md:text-3xl">
                    {t(step.titleKey)}
                  </span>
                  <span className="mt-1 block text-sm leading-relaxed text-muted group-data-[active=true]:text-ink/90">
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
