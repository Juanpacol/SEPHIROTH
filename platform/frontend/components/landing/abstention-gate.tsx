"use client";

import { useState } from "react";
import { useLanguage } from "@/lib/language";

const THRESHOLD = 50;

export default function AbstentionGate() {
  const { t } = useLanguage();
  const [value, setValue] = useState(75);
  const belowThreshold = value < THRESHOLD;

  return (
    <div className="card">
      <label htmlFor="evidence-strength" className="mb-2 block text-sm font-semibold">
        {t("marketing.abstention.evidenceStrength")}
      </label>
      <div className="relative mb-4">
        <input
          id="evidence-strength"
          type="range"
          min={0}
          max={100}
          value={value}
          onChange={(e) => setValue(Number(e.target.value))}
          aria-valuetext={
            belowThreshold ? t("marketing.abstention.belowThreshold") : t("marketing.abstention.aboveThreshold")
          }
          className="w-full accent-primary"
        />
        <div className="pointer-events-none absolute -top-1 h-3 w-px bg-danger/60" style={{ left: `${THRESHOLD}%` }} />
      </div>

      <div role="region" aria-live="polite">
        {belowThreshold ? (
          <div className="card border border-warning/40 bg-warning/10">
            <p className="text-sm font-semibold">{t("marketing.abstention.declineTitle")}</p>
            <p className="mt-1 text-sm text-muted">{t("marketing.abstention.declineBody")}</p>
          </div>
        ) : (
          <div className="card border border-primary/30 ai-ring">
            <p className="text-sm">{t("marketing.abstention.answerText")}</p>
          </div>
        )}
      </div>
    </div>
  );
}
