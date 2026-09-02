"use client";

import Link from "next/link";
import WingMark from "@/components/brand/wing-mark";
import { useLanguage } from "@/lib/language";

export default function LandingFooter() {
  const { t } = useLanguage();
  return (
    <footer className="border-t border-line/60">
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="grid gap-8 md:grid-cols-3">
          <div>
            <div className="flex items-center gap-2">
              <WingMark size={20} className="text-primary" />
              <span className="font-bold tracking-tight">SEPHIROTH</span>
            </div>
            <p className="mt-2 max-w-xs text-sm text-muted">{t("marketing.footer.tagline")}</p>
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("marketing.footer.product")}
            </div>
            <ul className="mt-2 space-y-1.5 text-sm">
              <li>
                <a href="#how-it-works" className="hover:text-primary">
                  {t("marketing.nav.howItWorks")}
                </a>
              </li>
              <li>
                <a href="#safeguards" className="hover:text-primary">
                  {t("marketing.nav.safeguards")}
                </a>
              </li>
              <li>
                <a href="#agents" className="hover:text-primary">
                  {t("marketing.nav.agents")}
                </a>
              </li>
            </ul>
          </div>

          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t("marketing.footer.getStarted")}
            </div>
            <ul className="mt-2 space-y-1.5 text-sm">
              <li>
                <Link href="/login" className="hover:text-primary">
                  {t("marketing.footer.clinicianSignIn")}
                </Link>
              </li>
              <li>
                <Link href="/portal/claim" className="hover:text-primary">
                  {t("marketing.footer.patientPortalSetup")}
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <p className="mt-10 text-xs text-muted">{t("common.footerDisclaimer")}</p>
      </div>
    </footer>
  );
}
