"use client";

/** One step of a consultation, as the product shows it. Used by the "how it works" story:
 * the same five stages, one per scroll position. Pure of state so any of them can be rendered
 * at any time. */

import AgentBadge from "@/components/agent-badge";
import {
  SAMPLE_QUESTION_KEY,
  SAMPLE_SPECIALISTS,
  SAMPLE_DRAFT_KEY,
  SAMPLE_GUARDED_KEY,
  SAMPLE_CLAIMS,
  CLAIM_LEGEND,
} from "@/lib/landing-content";
import { useLanguage } from "@/lib/language";

// The three agents that exist; the router picks exactly one of them.
const ROUTING_TAG_KEYS = [
  "marketing.agentName.evidence",
  "marketing.agentName.radiology",
  "marketing.agentName.drugSafety",
] as const;
const ROUTED_TAG_KEYS = new Set(["marketing.agentName.evidence"]);

type Translate = (key: string) => string;

/** One stage's content. Pure of state, so all five can be rendered at once. */
export default function StageBody({ render, t }: { render: string; t: Translate }) {
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
          <p className="mb-2 text-sm text-muted">{t("marketing.walkthrough.specialistLooks")}</p>
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
          <p className="mb-2 text-sm text-muted">{t("marketing.walkthrough.specialistWrites")}</p>
          <div className="card border border-primary/30 ai-ring">
            <div className="mb-2">
              <AgentBadge name={t("marketing.walkthrough.draftAnswer")} />
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
