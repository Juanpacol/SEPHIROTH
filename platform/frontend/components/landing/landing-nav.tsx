"use client";

/** The landing header, in the manner of the Ruby page: two headers, not one that changes.
 *
 * The first sits on the hero with no background and the page's navy palette, and goes away
 * with the hero as it scrolls. The second is a compact bar that stays out of sight (above the
 * screen, invisible) until the reader is past the hero, and then slides down; it is always
 * navy, so it needs no palette switching and never shows a colour that is not the page's.
 * Only one of them is in the accessibility tree at a time: the other is `inert`. */

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Menu } from "lucide-react";
import WingMark from "@/components/brand/wing-mark";
import ThemeToggle from "@/components/theme-toggle";
import Sheet from "@/components/ui/sheet";
import CtaButton from "./cta-button";
import Wordmark from "./wordmark";
import { useLanguage } from "@/lib/language";
import { pastHero } from "@/lib/scroll-effects";
import NavMenuBar from "./nav-menu-bar";
import { NAV_MENUS } from "./nav-menus";

/** React 18 does not know `inert`, and drops a boolean for an attribute it does not know:
 * it has to be given as an empty string, and left off when not wanted. */
const inertWhen = (on: boolean) => (on ? ({ inert: "" } as Record<string, string>) : {});

function HeaderRow({
  compact,
  onMenu,
  menuOpen,
}: {
  compact: boolean;
  onMenu: () => void;
  menuOpen: boolean;
}) {
  const { t } = useLanguage();
  return (
    <div
      className={`mx-auto flex max-w-6xl items-center justify-between px-6 transition-[height] duration-200 ${
        compact ? "h-14" : "h-[72px]"
      }`}
    >
      <Link href="/" className="group/brand flex items-center gap-2.5">
        <WingMark size={22} className="text-primary" />
        <Wordmark className="text-xl tracking-[0.1em] sm:text-[26px] sm:tracking-[0.16em]" />
      </Link>

      <NavMenuBar />

      <div className="flex items-center gap-2 md:gap-3">
        {/* The toggle moves into the sheet on a phone: logo + toggle + CTA
            together are wider than a 390px screen. */}
        <ThemeToggle className="hidden md:inline-flex" />
        <CtaButton href="/login" size="sm">
          {t("marketing.openApp")}
        </CtaButton>
        <button
          onClick={onMenu}
          className="tap -mr-2 rounded-full p-2 text-ink/70 hover:text-ink md:hidden"
          aria-label={t("nav.menu")}
          aria-expanded={menuOpen}
        >
          <Menu size={20} />
        </button>
      </div>
    </div>
  );
}

export default function LandingNav() {
  const { t } = useLanguage();
  const [menuOpen, setMenuOpen] = useState(false);
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    const update = () => {
      const hero = document.querySelector<HTMLElement>("[data-hero]");
      setCompact(pastHero(window.scrollY, hero?.offsetHeight ?? window.innerHeight));
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  return (
    <>
      {/* On the hero: no background of its own, and out of the way once the compact bar is shown. */}
      <header
        data-header="hero"
        {...inertWhen(compact)}
        aria-hidden={compact || undefined}
        className="band-dark absolute inset-x-0 top-0 z-20 !bg-transparent"
      >
        <HeaderRow compact={false} onMenu={() => setMenuOpen(true)} menuOpen={menuOpen} />
      </header>

      {/* Past the hero: a compact bar that slides down. `invisible` while it is away keeps it out
          of the tab order and the accessibility tree. */}
      <header
        data-header="compact"
        {...inertWhen(!compact)}
        aria-hidden={!compact || undefined}
        className={`band-dark fixed inset-x-0 top-0 z-40 border-b border-line/60 !bg-surface/85 backdrop-blur-md transition-[transform,visibility] duration-300 ease-out ${
          compact ? "visible translate-y-0" : "invisible -translate-y-full"
        }`}
      >
        <HeaderRow compact onMenu={() => setMenuOpen(true)} menuOpen={menuOpen} />
      </header>

      {/* An action sheet rather than a side drawer: these are jumps and links out of one
          page, not navigation into a section of an app. The same groups as the desktop menus,
          each item with its line. */}
      <Sheet open={menuOpen} onClose={() => setMenuOpen(false)} side="bottom" title={t("nav.menu")}>
        <div className="flex flex-col gap-4">
          {NAV_MENUS.map((menu) => (
            <nav key={menu.id} aria-label={t(menu.labelKey)}>
              <div className="eyebrow px-3 pb-1 text-muted">{t(menu.eyebrowKey)}</div>
              {menu.items.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  {...(item.external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                  className="tap flex items-start gap-3 rounded-inner px-3 py-2.5 hover:text-primary-ink"
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
    </>
  );
}
