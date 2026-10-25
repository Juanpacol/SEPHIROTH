"use client";

import WingMark from "@/components/brand/wing-mark";
import { useLanguage } from "@/lib/language";
import CtaButton from "./cta-button";
import { NAV_MENUS } from "./nav-menus";

/** Grain over the footer, same recipe as `feature-media.tsx`'s own `Grain` (and
 * `auth-backdrop.tsx`'s) — print texture over a flat colour. */
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 160 160' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.55'/%3E%3C/svg%3E\")";

/** The landing page's footer, built the way the Hermes Agent site (nousresearch.com) builds its
 * own (inspected with REA — see `docs/08-decisions` if this needs re-checking against a future
 * redesign there): one flat-coloured box, not a picture section stacked on top of a links
 * section. Everything — the oversized wordmark, the ink figure, the links — lives in the SAME
 * CSS grid cell (`*:col-start-1 *:row-start-1`), so paint order alone keeps the real content on
 * top; the wordmark can never visually collide with a column heading because it's rendered at
 * near-zero opacity (Hermes itself uses `opacity:.02` for theirs) rather than competing for
 * contrast. That one change is what earlier attempts at this kept missing: no fade-to-a-different
 * -colour seam, no clipped-vs-overlapping wordmark tradeoff, because there's only one surface.
 *
 * Its columns are the header's menus, so the two cannot disagree about where things are. */
export default function LandingFooter() {
  const { t } = useLanguage();
  return (
    <footer
      data-footer-reveal
      className="relative overflow-hidden border-t border-line/60 bg-[#1a2358] opacity-[calc(0.4+0.6*var(--footer-progress,1))]"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/landing/footer/ink-figure.webp"
        alt=""
        className="absolute inset-0 h-full w-full object-cover opacity-[0.07] mix-blend-soft-light [filter:grayscale(1)_contrast(1.1)]"
      />
      <div className="absolute inset-0 mix-blend-overlay opacity-20" style={{ backgroundImage: GRAIN }} />
      <span className="sr-only">{t("marketing.footer.stageAlt")}</span>

      <div className="relative mx-auto grid w-full max-w-6xl px-6 pb-10 pt-16 *:col-start-1 *:row-start-1 md:pt-24">
        {/* The watermark: SEPHIROTH at a whisper, filling the same box the content sits in —
            never clipped, never overlapping anything legible, because it barely reads at all. */}
        <p
          aria-hidden="true"
          className="pointer-events-none self-start whitespace-nowrap pt-2 text-center font-display text-[clamp(4rem,15vw,15rem)] font-light uppercase leading-none tracking-[0.02em] text-white/[0.06] opacity-[var(--footer-progress,1)]"
        >
          SEPHIROTH
        </p>

        <div
          data-footer-content
          className="translate-y-[var(--footer-lift,0px)] self-end opacity-[calc(0.35+0.65*var(--footer-progress,1))]"
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
