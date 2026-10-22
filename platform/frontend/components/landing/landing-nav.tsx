"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Menu } from "lucide-react";
import WingMark from "@/components/brand/wing-mark";
import ThemeToggle from "@/components/theme-toggle";
import Sheet from "@/components/ui/sheet";
import { ShimmerButton } from "@/components/magicui/shimmer-button";
import { useLanguage } from "@/lib/language";
import NavMenuBar from "./nav-menu-bar";
import { NAV_MENUS } from "./nav-menus";

export default function LandingNav() {
  const { t } = useLanguage();
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-20 transition-all duration-200 ${
        scrolled ? "glass-surface border-b border-line/60 shadow-raised" : ""
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2">
          <WingMark size={22} className="text-primary" />
          <span className="text-[15px] font-bold tracking-tight">SEPHIROTH</span>
        </Link>

        <NavMenuBar />

        <div className="flex items-center gap-2 md:gap-3">
          {/* The toggle moves into the sheet on a phone: logo + toggle + CTA
              together are wider than a 390px screen. */}
          <ThemeToggle className="hidden md:inline-flex" />
          <ShimmerButton href="/login" className="!px-4 !py-2 !text-sm">
            {t("marketing.openApp")}
          </ShimmerButton>
          <button
            onClick={() => setMenuOpen(true)}
            className="tap -mr-2 rounded-full p-2 text-ink/70 hover:bg-primary-soft hover:text-primary md:hidden"
            aria-label={t("nav.menu")}
            aria-expanded={menuOpen}
          >
            <Menu size={20} />
          </button>
        </div>
      </div>

      {/* An action sheet rather than a side drawer: these are jumps and links out of one
          page, not navigation into a section of an app. The same groups as the desktop menus,
          each item with its line. */}
      <Sheet open={menuOpen} onClose={() => setMenuOpen(false)} side="bottom" title={t("nav.menu")}>
        <div className="flex flex-col gap-4">
          {NAV_MENUS.map((menu) => (
            <nav key={menu.id} aria-label={t(menu.labelKey)}>
              <div className="eyebrow px-3 pb-1 text-muted">{t(menu.eyebrowKey)}</div>
              {[...(menu.promo ? [menu.promo] : []), ...menu.items].map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  {...(item.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                  className="tap flex items-start gap-3 rounded-inner px-3 py-2.5 hover:bg-primary-soft"
                >
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1.5 text-sm font-semibold">
                      {t(item.titleKey)}
                      {item.external ? (
                        <>
                          <ArrowUpRight size={13} aria-hidden="true" className="text-muted" />
                          <span className="sr-only">{t("marketing.nav.external")}</span>
                        </>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-muted">{t(item.bodyKey)}</span>
                  </span>
                </a>
              ))}
            </nav>
          ))}
        </div>
        <div className="mt-4 flex justify-center border-t border-line/60 pt-4">
          <ThemeToggle />
        </div>
      </Sheet>
    </header>
  );
}
