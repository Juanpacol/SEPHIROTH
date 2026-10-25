"use client";

import WingMark from "@/components/brand/wing-mark";
import { useLanguage } from "@/lib/language";
import CtaButton from "./cta-button";
import { NAV_MENUS } from "./nav-menus";

/** Grain over the stage, same recipe as `feature-media.tsx`'s own `Grain` (and
 * `auth-backdrop.tsx`'s) — print texture over a flat gradient. */
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 160 160' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.55'/%3E%3C/svg%3E\")";

/** The vignette that keeps the ink figure a soft presence inside the stage rather than a
 * picture with visible edges: full strength in the middle, faded to nothing well before the
 * stage's own border on every side. */
const STAGE_IMAGE_MASK = "radial-gradient(120% 95% at 50% 38%, black 40%, transparent 82%)";

/** The landing page's footer, as the Hermes page builds its own: a full screen on its own. A picture fills
 * the top and fades into the page, the name climbs up out of its bottom edge, and the links sit under it,
 * all driven by how far the footer is in view (`components/landing/scroll-effects.tsx` sets
 * `--footer-progress` and `--footer-lift`). The footer stays in the normal flow, so its
 * links are always where focus and reading order expect them. Every variable has a
 * resting default, so without the script, or with reduced motion, it is simply there.
 *
 * One gradient — the page's own blue, fading to its `surface` colour — runs behind the whole
 * footer, stage and links alike, so the links never sit on a flat block that looks like a
 * different page bolted underneath the stage, and the oversized wordmark (which overlaps the
 * links section by design) tapers into a colour that already matches instead of being cut by
 * a visibly different one.
 *
 * Its columns are the header's menus, so the two cannot disagree about where things are. */
export default function LandingFooter() {
  const { t } = useLanguage();
  return (
    <footer
      data-footer-reveal
      className="relative overflow-hidden border-t border-line/60 opacity-[calc(0.4+0.6*var(--footer-progress,1))] md:flex md:min-h-dvh md:flex-col"
    >
      {/* One backdrop for the whole footer: the page's blue, settling into its surface colour
          well before the links, so stage and links read as one continuous surface. */}
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-[linear-gradient(to_bottom,#243473_0%,#1f2fa0_20%,rgb(var(--color-surface))_62%,rgb(var(--color-surface))_100%)]"
      />

      {/* The stage: the ink figure as soft texture, a grain pass, and the name rising out of
          the bottom edge against the shared backdrop above. Only the picture's own layer clips
          (so its vignette has a hard edge to fade inside of) — the name itself isn't clipped
          here, so it tapers into the links section's matching colour, not a hard line. */}
      <div className="relative isolate h-[55dvh] min-h-[360px] md:h-auto md:flex-auto">
        <div aria-hidden="true" className="absolute inset-0 overflow-hidden">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/landing/footer/ink-figure.webp"
            alt=""
            className="absolute inset-0 h-full w-full object-cover opacity-35 mix-blend-soft-light [filter:grayscale(1)_contrast(1.1)]"
            style={{ maskImage: STAGE_IMAGE_MASK, WebkitMaskImage: STAGE_IMAGE_MASK }}
          />
          <div className="absolute inset-0 mix-blend-overlay opacity-25" style={{ backgroundImage: GRAIN }} />
        </div>
        <span className="sr-only">{t("marketing.footer.stageAlt")}</span>
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 flex select-none justify-center"
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
