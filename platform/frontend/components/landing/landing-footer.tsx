"use client";

import WingMark from "@/components/brand/wing-mark";
import { useLanguage } from "@/lib/language";
import CtaButton from "./cta-button";
import FeatureMediaView from "./feature-media";
import { NAV_MENUS } from "./nav-menus";

/** The picture that fills the top of the footer: an ink wave, in the page's blue. */
const STAGE = {
  kind: "image",
  src: "/landing/features/follow-waveform.webp",
  altKey: "marketing.features.follow.alt",
} as const;

/** The landing page's footer, as the Hermes page builds its own: a full screen on its own. A picture fills
 * the top and fades into the page, the name climbs up out of its bottom edge, and the links sit under it,
 * all driven by how far the footer is in view (`components/landing/scroll-effects.tsx` sets
 * `--footer-progress` and `--footer-lift`). The footer stays in the normal flow, so its
 * links are always where focus and reading order expect them. Every variable has a
 * resting default, so without the script, or with reduced motion, it is simply there.
 *
 * Its columns are the header's menus, so the two cannot disagree about where things are. */
export default function LandingFooter() {
  const { t } = useLanguage();
  return (
    <footer
      data-footer-reveal
      className="relative overflow-hidden border-t border-line/60 opacity-[calc(0.4+0.6*var(--footer-progress,1))] md:flex md:min-h-dvh md:flex-col"
    >
      {/* The stage: a picture, a fade into the page's navy, and the name rising out of the bottom edge. */}
      <div className="relative isolate h-[55dvh] min-h-[360px] md:h-auto md:flex-auto">
        <div aria-hidden="true" className="absolute inset-0 opacity-70">
          <FeatureMediaView media={STAGE} />
        </div>
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-b from-surface via-transparent to-surface"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 flex select-none justify-center overflow-hidden"
        >
          <span
            data-footer-wordmark
            className="translate-y-[calc(12%+(1-var(--footer-progress,1))*55%)] whitespace-nowrap font-display text-[clamp(4.5rem,21vw,22rem)] font-light uppercase leading-[0.82] tracking-[0.04em] text-white/[0.92] opacity-[var(--footer-progress,1)]"
          >
            SEPHIROTH
          </span>
        </div>
      </div>

      <div className="relative mx-auto w-full max-w-6xl px-6 pb-10 pt-12 md:pb-12">
        <div
          data-footer-content
          className="translate-y-[var(--footer-lift,0px)] opacity-[calc(0.35+0.65*var(--footer-progress,1))]"
        >
          <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <div>
              <div className="flex items-center gap-2">
                <WingMark size={22} className="text-primary-ink" />
                <span className="font-bold tracking-tight">SEPHIROTH</span>
              </div>
              <p className="mt-3 max-w-xs text-sm text-muted">{t("marketing.footer.tagline")}</p>
              <CtaButton href="/login" size="sm" className="mt-6">
                {t("marketing.footer.clinicianSignIn")}
              </CtaButton>
            </div>

            {NAV_MENUS.map((menu) => (
              <nav key={menu.id} aria-label={t(menu.labelKey)}>
                <div className="eyebrow text-muted">{t(menu.eyebrowKey)}</div>
                <h2 className="mt-1 font-display text-2xl font-light uppercase tracking-wide">
                  {t(menu.labelKey)}
                </h2>
                <ul className="mt-3 space-y-1">
                  {menu.items.map((item) => (
                    <li key={item.href}>
                      <a
                        href={item.href}
                        {...(item.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                        className="tap nav-underline inline-flex items-center px-0 font-mono text-[11px] uppercase tracking-[0.16em] text-ink/75 transition-colors duration-normal ease-standard hover:text-ink [&::after]:left-0 [&::after]:right-0 [&::after]:bottom-2"
                      >
                        {t(item.titleKey)}
                        {item.external ? (
                          <span className="sr-only">{t("marketing.nav.external")}</span>
                        ) : null}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            ))}
          </div>

          <div className="mt-14 flex flex-col gap-2 border-t border-line/60 pt-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
            <p>{t("common.footerDisclaimer")}</p>
            <p className="eyebrow">© SEPHIROTH</p>
          </div>
        </div>
      </div>
    </footer>
  );
}
