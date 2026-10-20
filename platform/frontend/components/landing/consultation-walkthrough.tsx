"use client";

/** The landing page's centerpiece: click through (or auto-play) the five
 * stages of a real consultation. Autoplay starts immediately on mount —
 * a first-time visitor shouldn't have to click Play to see the point —
 * but pauses on hover/focus, and never starts at all under
 * `prefers-reduced-motion: reduce` (checked once on mount; the
 * accessibility guidance against auto-advancing content applies to the
 * *default* behavior, satisfied here by respecting that media query
 * rather than by requiring an explicit click from every visitor).
 *
 * The panel never changes height: all five stages share one grid cell, so it is
 * as tall as the tallest and the hero does not resize (and push the rest of the
 * page around) each time autoplay moves on. */

import { useEffect, useRef, useState } from "react";
import { Play, Pause } from "lucide-react";
import AgentBadge from "@/components/agent-badge";
import {
  WALKTHROUGH_STAGES,
  SAMPLE_QUESTION_KEY,
  SAMPLE_SPECIALISTS,
  SAMPLE_DRAFT_KEY,
  SAMPLE_GUARDED_KEY,
  SAMPLE_CLAIMS,
  CLAIM_LEGEND,
} from "@/lib/landing-content";
import { useLanguage } from "@/lib/language";

const ROUTING_TAG_KEYS = [
  "marketing.agentName.evidence",
  "marketing.agentName.laboratory",
  "marketing.agentName.radiology",
  "marketing.agentName.drugSafety",
] as const;
const ROUTED_TAG_KEYS = new Set(["marketing.agentName.evidence", "marketing.agentName.laboratory"]);

type Translate = (key: string) => string;

/** One stage's content. Pure of state, so all five can be rendered at once. */
function StageBody({ render, t }: { render: string; t: Translate }) {
  return (
    <>
      {render === "routing" && (
        <div>
          <p className="mb-4 text-sm text-muted">{t("marketing.walkthrough.clinicianAsks")}</p>
          <p className="card border border-line/70 text-sm font-medium">{t(SAMPLE_QUESTION_KEY)}</p>
          <p className="mt-4 text-sm text-muted">{t("marketing.walkthrough.routerExplainer")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {ROUTING_TAG_KEYS.map((nameKey) => (
              <span
                key={nameKey}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                  ROUTED_TAG_KEYS.has(nameKey)
                    ? "bg-primary text-white"
                    : "bg-surface text-muted line-through"
                }`}
              >
                {t(nameKey)}
              </span>
            ))}
          </div>
        </div>
      )}

      {render === "specialists" && (
        <div className="space-y-3">
          <p className="mb-2 text-sm text-muted">{t("marketing.walkthrough.specialistsRunIndependently")}</p>
          {SAMPLE_SPECIALISTS.map((s) => (
            <div key={s.nameKey} className="card border border-line/70">
              <div className="mb-1 flex items-center gap-2">
                <AgentBadge name={t(s.nameKey)} />
              </div>
              <p className="text-sm">{t(s.findingKey)}</p>
            </div>
          ))}
        </div>
      )}

      {render === "synthesize" && (
        <div>
          <p className="mb-2 text-sm text-muted">{t("marketing.walkthrough.coordinatorMerges")}</p>
          <div className="card border border-primary/30 ai-ring">
            <div className="mb-2">
              <AgentBadge name={t("marketing.walkthrough.coordinatorDraft")} />
            </div>
            <p className="text-sm">{t(SAMPLE_DRAFT_KEY)}</p>
          </div>
        </div>
      )}

      {render === "guard" && (
        <div>
          <p className="mb-2 text-sm text-muted">{t("marketing.walkthrough.guardExplainer")}</p>
          <div className="card border border-line/70">
            <p className="text-sm">
              {t("marketing.walkthrough.guardTextPre")}{" "}
              <span className="text-danger line-through opacity-60">
                {t("marketing.walkthrough.guardStrikethrough")}
              </span>{" "}
              → <span className="font-semibold text-danger">{t("marketing.walkthrough.unverifiedRemoved")}</span>
              {t("marketing.walkthrough.guardTextPost")}
            </p>
          </div>
          <p className="mt-2 text-xs text-muted">
            {t("marketing.walkthrough.guardResultLabel")} <span className="font-mono">{t(SAMPLE_GUARDED_KEY)}</span>
          </p>
        </div>
      )}

      {render === "verify" && (
        <div>
          <p className="mb-2 text-sm text-muted">{t("marketing.walkthrough.verifyExplainer")}</p>
          <div className="mb-3 flex flex-wrap gap-3 text-xs">
            {CLAIM_LEGEND.map((l) => (
              <span key={l.state} className={`font-semibold ${l.color}`}>
                ● {t(l.labelKey)}
              </span>
            ))}
          </div>
          <div className="space-y-2">
            {SAMPLE_CLAIMS.map((c) => (
              <div key={c.textKey} className="card border border-line/70 py-2.5">
                <p className="text-sm">{t(c.textKey)}</p>
                <p className="mt-1 text-xs text-muted">{t(c.actionKey)}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export default function ConsultationWalkthrough() {
  const { t } = useLanguage();
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    setPlaying(true);
  }, []);

  useEffect(() => {
    if (!playing) return;
    intervalRef.current = setInterval(() => {
      setIndex((i) => (i + 1) % WALKTHROUGH_STAGES.length);
    }, 2200);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing]);

  return (
    <div
      className="overflow-hidden rounded-squircle border border-line/60 bg-card shadow-card"
      onMouseEnter={() => setPlaying(false)}
      onFocus={() => setPlaying(false)}
    >
      <div className="flex items-center gap-2 border-b border-line/60 bg-surface/60 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-danger/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-warning/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-success/70" />
        <span className="ml-2 font-mono text-[11px] text-muted">{t("marketing.walkthrough.windowTitle")}</span>
      </div>

      <div className="p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div
            role="tablist"
            aria-label={t("marketing.walkthrough.stagesLabel")}
            className="flex flex-wrap items-center gap-1.5"
          >
            {WALKTHROUGH_STAGES.map((s, i) => (
              <button
                key={s.id}
                role="tab"
                aria-selected={i === index}
                onClick={() => setIndex(i)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors motion-reduce:transition-none ${
                  i === index ? "bg-primary text-white" : "bg-primary-soft text-primary hover:brightness-95"
                }`}
              >
                {t(s.labelKey)}
              </button>
            ))}
          </div>
          <button
            onClick={() => setPlaying((p) => !p)}
            aria-label={playing ? t("marketing.walkthrough.pause") : t("marketing.walkthrough.runIt")}
            className="btn-secondary py-1.5 text-xs"
          >
            {playing ? <Pause size={13} /> : <Play size={13} />}
            {playing ? t("marketing.walkthrough.pause") : t("marketing.walkthrough.runIt")}
          </button>
        </div>

        {/* Every stage sits in the same grid cell and only the current one is shown, so
            the panel is always as tall as the tallest stage. It used to follow each
            stage's own height, which made the whole hero (and everything below it)
            grow and shrink every 2.2s on its own while autoplay ran. A hidden stage
            is `invisible`, not removed: out of the tab order and the accessibility
            tree, but still counted in the layout. */}
        <div className="grid">
          {WALKTHROUGH_STAGES.map((s, i) => (
            <div
              key={s.id}
              role="tabpanel"
              aria-live={i === index ? "polite" : "off"}
              className={`col-start-1 row-start-1 ${
                i === index ? "animate-fadeIn motion-reduce:animate-none" : "invisible"
              }`}
            >
              <StageBody render={s.render} t={t} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
