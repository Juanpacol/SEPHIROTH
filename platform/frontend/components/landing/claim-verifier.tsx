"use client";

import { useState } from "react";
import { CLAIM_LEGEND, SAMPLE_CLAIMS } from "@/lib/landing-content";
import { useLanguage } from "@/lib/language";

export default function ClaimVerifier() {
  const { t } = useLanguage();
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <div className="card">
      <div className="mb-4 flex flex-wrap gap-3 text-xs">
        {CLAIM_LEGEND.map((l) => (
          <span key={l.state} className={`font-semibold ${l.color}`}>
            ● {t(l.labelKey)}
          </span>
        ))}
      </div>

      <div className="space-y-2">
        {SAMPLE_CLAIMS.map((claim, i) => {
          const legend = CLAIM_LEGEND.find((l) => l.state === claim.state)!;
          const expanded = openIndex === i;
          return (
            <div key={claim.textKey}>
              <button
                aria-expanded={expanded}
                aria-controls={`claim-panel-${i}`}
                onClick={() => setOpenIndex(expanded ? null : i)}
                className="flex w-full items-start gap-2 rounded-xl px-2 py-2 text-left text-sm hover:bg-primary-soft/40"
              >
                <span className={`mt-0.5 shrink-0 font-bold ${legend.color}`}>●</span>
                <span className="underline decoration-dotted underline-offset-2">{t(claim.textKey)}</span>
              </button>
              {expanded && (
                <div
                  id={`claim-panel-${i}`}
                  className="ml-6 mt-1 rounded-xl border border-line/70 p-3 text-sm animate-fadeIn"
                >
                  <div className={`mb-1 text-xs font-semibold ${legend.color}`}>{t(legend.labelKey)}</div>
                  <p className="text-muted">{t(claim.evidenceKey)}</p>
                  <p className="mt-2 font-medium">{t(claim.actionKey)}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
