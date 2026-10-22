"use client";

/** The landing hero's picture of the product: an answer as SEPHIROTH gives it, a question,
 * the specialist that took it, an answer with its sources, a check of each claim, and how
 * it ended (answered, or declined for want of evidence). It cycles through three
 * examples (`lib/landing-answers.ts`) and builds each up piece by piece.
 *
 * It is a picture, not a terminal: it looks like the app. What it says is written for the
 * page and labelled as an example; nothing here calls a model.
 *
 * Height never changes. Every example is also rendered invisibly in the same grid cell, so
 * the card is as tall as the tallest and nothing below the hero moves when the example
 * changes. It stops cycling on hover and on focus, has a pause button (content that moves
 * by itself for more than five seconds needs one), and under reduced motion it shows the
 * first example, finished, and only changes when the reader picks another. */

import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import AgentBadge from "@/components/agent-badge";
import { ANSWER_EXAMPLES, type AnswerExample } from "@/lib/landing-answers";
import { CLAIM_LEGEND } from "@/lib/landing-content";
import { useLanguage } from "@/lib/language";

const EXAMPLE_MS = 8000;

const LEGEND = Object.fromEntries(CLAIM_LEGEND.map((l) => [l.state, l]));

/** One example, drawn. Each part has its own entrance delay, so the answer builds up in the
 * order a reader takes it in. `delay` is zero for the sizing copies, which never show. */
function Example({ example, build }: { example: AnswerExample; build: boolean }) {
  const { t } = useLanguage();
  // Each part's entrance delay, also written as `data-delay` so it can be read back.
  const step = (ms: number) => ({
    style: build
      ? ({ animationDelay: `${ms}ms`, animationFillMode: "both" } as React.CSSProperties)
      : undefined,
    "data-delay": build ? ms : undefined,
  });
  const enter = build ? "animate-toast-in" : "";
  const declined = example.outcome === "decline";

  return (
    <div className="flex flex-col gap-4">
      <div className={enter} {...step(0)}>
        <div className="eyebrow mb-2 text-muted">{t("marketing.answer.you")}</div>
        <p className="rounded-inner bg-primary-soft px-4 py-3 text-sm font-medium">
          {t(example.questionKey)}
        </p>
      </div>

      <div className={`rounded-inner border border-line/70 bg-surface/60 p-4 ${enter}`} {...step(500)}>
        <AgentBadge name={t(example.agentKey)} />
        <p className="mt-3 text-[15px] leading-relaxed">{t(example.answerKey)}</p>
        {example.citations.length > 0 ? (
          <ul className="mt-3 flex flex-wrap gap-2">
            {example.citations.map((c) => (
              <li
                key={c}
                className="eyebrow rounded-full border border-line px-2.5 py-1 normal-case text-primary-ink"
              >
                [{c}]
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <ul className={`flex flex-col gap-2 ${enter}`} {...step(1100)}>
        {example.claims.map((claim) => {
          const legend = LEGEND[claim.state];
          return (
            <li key={claim.textKey} className="flex items-start gap-2.5 text-sm">
              <span aria-hidden="true" className={`mt-0.5 font-bold ${legend.color}`}>
                ●
              </span>
              <span className="min-w-0">
                {t(claim.textKey)}
                <span className={`ml-2 text-xs font-semibold ${legend.color}`}>{t(legend.labelKey)}</span>
              </span>
            </li>
          );
        })}
      </ul>

      <div className={enter} {...step(1700)}>
        <span
          className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
            declined ? "bg-warning/15 text-warning" : "bg-success/15 text-success"
          }`}
        >
          {t(example.outcomeKey)}
        </span>
      </div>
    </div>
  );
}

export default function AnswerCard() {
  const { t } = useLanguage();
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [held, setHeld] = useState(false);
  const [reduce, setReduce] = useState(true);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  // Decided after mount: the server has no way to know, and starting still is the safe default.
  useEffect(() => {
    setReduce(
      typeof window.matchMedia === "function" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    );
  }, []);

  useEffect(() => {
    if (reduce || paused || held) return;
    const id = setTimeout(() => setIndex((i) => (i + 1) % ANSWER_EXAMPLES.length), EXAMPLE_MS);
    return () => clearTimeout(id);
  }, [index, reduce, paused, held]);

  const move = (to: number) => {
    const next = (to + ANSWER_EXAMPLES.length) % ANSWER_EXAMPLES.length;
    setIndex(next);
    tabs.current[next]?.focus();
  };

  return (
    <div
      data-testid="answer-card"
      className="card w-full min-w-0 max-w-xl !p-5 text-left shadow-raised-lg sm:!p-6"
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <div className="mb-5 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <span className="eyebrow text-muted">{t("marketing.answer.label")}</span>
        <div className="flex items-center gap-1">
          <div role="tablist" aria-label={t("marketing.answer.tabs")} className="flex flex-wrap gap-1">
            {ANSWER_EXAMPLES.map((example, i) => (
              <button
                key={example.id}
                ref={(el) => {
                  tabs.current[i] = el;
                }}
                role="tab"
                id={`answer-tab-${example.id}`}
                aria-selected={i === index}
                aria-controls="answer-panel"
                tabIndex={i === index ? 0 : -1}
                onClick={() => setIndex(i)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowRight") move(i + 1);
                  else if (e.key === "ArrowLeft") move(i - 1);
                  else return;
                  e.preventDefault();
                }}
                className={`tap rounded-full px-3 py-1.5 text-xs font-semibold transition-colors duration-normal ${
                  i === index ? "bg-primary-fill text-white" : "text-muted hover:text-primary-ink"
                }`}
              >
                {t(example.tabKey)}
              </button>
            ))}
          </div>
          {reduce ? null : (
            <button
              type="button"
              onClick={() => setPaused((p) => !p)}
              aria-label={t(paused ? "marketing.answer.play" : "marketing.answer.pause")}
              className="tap grid place-items-center rounded-full text-muted hover:text-primary-ink"
            >
              {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}
            </button>
          )}
        </div>
      </div>

      <div
        id="answer-panel"
        role="tabpanel"
        aria-labelledby={`answer-tab-${ANSWER_EXAMPLES[index].id}`}
        aria-live="off"
      >
        <div className="grid">
          {/* Invisible copies of every example, so the card is as tall as the tallest. */}
          {ANSWER_EXAMPLES.map((example) => (
            <div key={example.id} aria-hidden="true" className="invisible col-start-1 row-start-1">
              <Example example={example} build={false} />
            </div>
          ))}
          {/* The one on show; a new key restarts its entrance. */}
          <div key={ANSWER_EXAMPLES[index].id} className="col-start-1 row-start-1">
            <Example example={ANSWER_EXAMPLES[index]} build={!reduce} />
          </div>
        </div>
      </div>
    </div>
  );
}
