"use client";

import { useState } from "react";
import { useLanguage } from "@/lib/language";

export default function CitationGuardToggle() {
  const { t } = useLanguage();
  const [mode, setMode] = useState<"raw" | "guarded">("raw");

  return (
    <div className="card">
      <div
        role="radiogroup"
        aria-label={t("marketing.citationToggle.groupLabel")}
        className="mb-4 inline-flex items-center gap-0.5 rounded-full bg-primary-soft p-1"
      >
        {(["raw", "guarded"] as const).map((value) => (
          <button
            key={value}
            role="radio"
            aria-checked={mode === value}
            onClick={() => setMode(value)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
              mode === value ? "bg-card text-primary shadow-sm" : "text-muted hover:text-primary"
            }`}
          >
            {value === "raw" ? t("marketing.citationToggle.raw") : t("marketing.citationToggle.guarded")}
          </button>
        ))}
      </div>

      {mode === "raw" ? (
        <p className="text-sm" hidden={mode !== "raw"}>
          {t("marketing.walkthrough.guardTextPre")}{" "}
          <span className="rounded bg-danger/10 px-1 text-danger">
            {t("marketing.walkthrough.guardStrikethrough")}
          </span>
          {t("marketing.walkthrough.guardTextPost")}
        </p>
      ) : (
        <div hidden={mode !== "guarded"}>
          <p className="text-sm">
            {t("marketing.walkthrough.guardTextPre")} {t("marketing.walkthrough.unverifiedRemoved")}
            {t("marketing.walkthrough.guardTextPost")}
          </p>
          <p className="mt-2 text-xs text-muted">{t("marketing.citationToggle.removedNote")}</p>
        </div>
      )}
    </div>
  );
}
