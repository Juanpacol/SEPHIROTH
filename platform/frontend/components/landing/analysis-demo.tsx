"use client";

/** The landing page's imaging demo: pick a study and read the analysis a vision model
 * wrote for it, next to the image. It answers "what does an analysis look like?"
 * before anyone signs up. Everything here is static (`lib/imaging-demo.ts`): the
 * public page never calls a model and never touches patient data.
 *
 * Like the consultation walkthrough above it, every study's panel sits in one grid
 * cell and the inactive ones are `invisible`, so the section is as tall as the
 * tallest and nothing below it moves when the study changes. */

import { useRef, useState } from "react";
import { DEMO_STUDIES } from "@/lib/imaging-demo";
import { useLanguage } from "@/lib/language";

const MODALITY_KEYS: Record<string, string> = {
  XRAY: "marketing.demo.modality.xray",
  CT: "marketing.demo.modality.ct",
  MRI: "marketing.demo.modality.mri",
  ULTRASOUND: "marketing.demo.modality.ultrasound",
};

export default function AnalysisDemo() {
  const { t } = useLanguage();
  const [active, setActive] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = (to: number) => {
    const next = (to + DEMO_STUDIES.length) % DEMO_STUDIES.length;
    setActive(next);
    tabs.current[next]?.focus();
  };

  return (
    <div data-testid="analysis-demo">
      <div role="tablist" aria-label={t("marketing.demo.tabsLabel")} className="mb-5 flex flex-wrap gap-2">
        {DEMO_STUDIES.map((study, i) => (
          <button
            key={study.id}
            ref={(el) => {
              tabs.current[i] = el;
            }}
            role="tab"
            id={`demo-tab-${study.id}`}
            aria-selected={i === active}
            aria-controls={`demo-panel-${study.id}`}
            tabIndex={i === active ? 0 : -1}
            onClick={() => setActive(i)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") move(i + 1);
              else if (e.key === "ArrowLeft") move(i - 1);
              else if (e.key === "Home") move(0);
              else if (e.key === "End") move(DEMO_STUDIES.length - 1);
              else return;
              e.preventDefault();
            }}
            className={`tap rounded-full px-4 py-2 text-sm font-semibold transition-colors duration-normal ${
              i === active
                ? "bg-primary-fill text-white"
                : "bg-card text-ink/80 shadow-hairline hover:text-primary-ink"
            }`}
          >
            {t(MODALITY_KEYS[study.modality] ?? "marketing.demo.modality.xray")} · {study.region}
          </button>
        ))}
      </div>

      <div className="grid">
        {DEMO_STUDIES.map((study, i) => (
          <div
            key={study.id}
            role="tabpanel"
            id={`demo-panel-${study.id}`}
            aria-labelledby={`demo-tab-${study.id}`}
            aria-hidden={i !== active}
            className={`col-start-1 row-start-1 grid grid-cols-1 gap-6 transition-opacity duration-normal lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] ${
              i === active ? "opacity-100" : "invisible opacity-0"
            }`}
          >
            <div className="aspect-[4/3] overflow-hidden rounded-inner bg-surface">
              {/* A static, optimised-at-build file from /public; no remote asset for next/image to fetch. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={study.image}
                alt={`${t(MODALITY_KEYS[study.modality] ?? "marketing.demo.modality.xray")} · ${study.region}`}
                className="media-edge h-full w-full object-cover"
                loading="lazy"
              />
            </div>
            <div className="card flex flex-col justify-center gap-3">
              <span className="eyebrow text-primary-ink">{t("marketing.demo.analysis")}</span>
              <p className="text-sm leading-relaxed text-ink/90">{study.description}</p>
              <p className="text-xs text-muted">{t("marketing.demo.language")}</p>
              <p className="text-xs text-muted">
                {t("marketing.demo.model").replace("{model}", study.model)} {t("marketing.demo.note")}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
