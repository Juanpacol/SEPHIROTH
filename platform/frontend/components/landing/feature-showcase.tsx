"use client";

/** The landing page's feature showcase, in the manner of the Hermes Agent site: a numbered
 * list of what the product does on one side and, beside it, a media panel that stays in
 * view and changes with the feature you are reading.
 *
 * From `lg` up the panel is sticky and shows the media of the feature in the middle of the
 * screen (its layers cross-fade, the new one revealed from the top down). Below `lg` there
 * is no sticky panel: each feature carries its own media above its text. Both come from the
 * same data, so they cannot disagree. The media itself is configured in
 * `lib/landing-features.ts`. */

import { useActiveSection } from "@/lib/hooks/use-active-section";
import { LANDING_FEATURES } from "@/lib/landing-features";
import { useLanguage } from "@/lib/language";
import FeatureMediaView from "./feature-media";

const ARTICLE_IDS = LANDING_FEATURES.map((f) => `feature-${f.id}`);

export default function FeatureShowcase() {
  const { t } = useLanguage();
  const current = useActiveSection(ARTICLE_IDS);
  const activeIndex = Math.max(0, ARTICLE_IDS.indexOf(current ?? ARTICLE_IDS[0]));

  return (
    <div className="grid grid-cols-1 gap-x-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <ol className="flex flex-col">
        {LANDING_FEATURES.map((feature, i) => {
          const verb = t(feature.verbKey);
          const active = i === activeIndex;
          return (
            <li key={feature.id}>
              <article
                id={`feature-${feature.id}`}
                aria-labelledby={`feature-${feature.id}-title`}
                data-active={active || undefined}
                className="flex flex-col justify-center gap-5 py-10 lg:min-h-[72vh] lg:py-16"
              >
                <div className="aspect-[4/3] overflow-hidden rounded-card shadow-raised lg:hidden">
                  <FeatureMediaView media={feature.media} index={i} verb={verb} still />
                </div>
                <div
                  className={`border-l-2 pl-5 transition-colors duration-slow ease-standard ${
                    active ? "border-primary" : "border-line"
                  }`}
                >
                  <div className="eyebrow text-primary-ink">
                    {String(i + 1).padStart(2, "0")} · {verb}
                  </div>
                  <h3
                    id={`feature-${feature.id}-title`}
                    className="mt-2 font-display text-title font-semibold"
                  >
                    {t(feature.titleKey)}
                  </h3>
                  <p className="mt-3 max-w-md text-muted">{t(feature.bodyKey)}</p>
                </div>
              </article>
            </li>
          );
        })}
      </ol>

      <div className="hidden lg:block">
        <div className="sticky top-28 py-10">
          <div
            data-testid="feature-panel"
            className="relative aspect-[4/3] overflow-hidden rounded-card bg-surface shadow-raised-lg"
          >
            {LANDING_FEATURES.map((feature, i) => {
              const active = i === activeIndex;
              return (
                <div
                  key={feature.id}
                  data-layer={feature.id}
                  aria-hidden={!active}
                  className={`absolute inset-0 transition-[opacity,clip-path] duration-slow ease-sheet ${
                    active ? "opacity-100 [clip-path:inset(0)]" : "opacity-0 [clip-path:inset(0_0_100%_0)]"
                  }`}
                >
                  <FeatureMediaView
                    media={feature.media}
                    index={i}
                    verb={t(feature.verbKey)}
                    playing={active}
                  />
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
