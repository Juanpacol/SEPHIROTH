"use client";

/** The landing page's centerpiece: click through (or auto-play) the five
 * stages of a real consultation. Autoplay is off by default and only
 * starts on explicit click, per the accessibility guidance for
 * auto-advancing content — it also pauses on hover/focus. Under
 * `prefers-reduced-motion: reduce`, transitions collapse via the
 * `motion-reduce:` utility and the "thinking" dots render as static text
 * instead of animating. */

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

export default function ConsultationWalkthrough() {
  const { t } = useLanguage();
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!playing) return;
    intervalRef.current = setInterval(() => {
      setIndex((i) => (i + 1) % WALKTHROUGH_STAGES.length);
    }, 2200);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing]);

  const stage = WALKTHROUGH_STAGES[index];

  return (
    <div
      className="card"
      onMouseEnter={() => setPlaying(false)}
      onFocus={() => setPlaying(false)}
    >
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

      <div
        role="tabpanel"
        aria-live="polite"
        className="min-h-[22rem] animate-fadeIn motion-reduce:animate-none"
        key={stage.id}
      >
        {stage.render === "routing" && (
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

        {stage.render === "specialists" && (
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

        {stage.render === "synthesize" && (
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

        {stage.render === "guard" && (
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

        {stage.render === "verify" && (
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
      </div>
    </div>
  );
}
