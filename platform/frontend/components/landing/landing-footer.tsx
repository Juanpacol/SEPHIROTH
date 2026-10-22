"use client";

import Link from "next/link";
import WingMark from "@/components/brand/wing-mark";
import { useLanguage } from "@/lib/language";
import { NAV_MENUS } from "./nav-menus";

/** The landing page's footer, a navy band that comes up as the reader reaches the end:
 * its content fades and rises, and the name behind it climbs into place, all driven by
 * how far the footer is in view (`components/landing/scroll-effects.tsx` sets
 * `--footer-progress` and `--footer-lift`). The footer stays in the normal flow, so its
 * links are always where focus and reading order expect them. Every variable has a
 * resting default, so without the script, or with reduced motion, it is simply there.
 *
 * Its columns are the header's menus, so the two cannot disagree about where things are. */
export default function LandingFooter() {
  const { t } = useLanguage();
  return (
    <footer data-footer-reveal className="band-dark relative overflow-hidden border-t border-line/60">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 flex select-none justify-center overflow-hidden"
      >
        <span
          data-footer-wordmark
          className="translate-y-[calc((1-var(--footer-progress,1))*45%)] whitespace-nowrap font-display text-[clamp(5rem,23vw,19rem)] font-semibold leading-[0.82] tracking-tight text-ink/[0.07]"
        >
          SEPHIROTH
        </span>
      </div>

      <div className="relative mx-auto max-w-6xl px-6 pb-16 pt-16 md:pb-24">
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
              <Link href="/login" className="btn-primary mt-6 inline-flex">
                {t("marketing.footer.clinicianSignIn")}
              </Link>
            </div>

            {NAV_MENUS.map((menu) => (
              <nav key={menu.id} aria-label={t(menu.labelKey)}>
                <div className="eyebrow text-muted">{t(menu.eyebrowKey)}</div>
                <h2 className="mt-1 font-display text-2xl font-semibold">{t(menu.labelKey)}</h2>
                <ul className="mt-3 space-y-1">
                  {menu.items.map((item) => (
                    <li key={item.href}>
                      <a
                        href={item.href}
                        {...(item.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                        className="tap inline-flex items-center text-sm text-ink/80 hover:text-primary-ink"
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
