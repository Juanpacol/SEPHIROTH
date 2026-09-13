"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Menu } from "lucide-react";
import WingMark from "@/components/brand/wing-mark";
import ThemeToggle from "@/components/theme-toggle";
import Sheet from "@/components/ui/sheet";
import { ShimmerButton } from "@/components/magicui/shimmer-button";
import { useLanguage } from "@/lib/language";

const LINKS = [
  { href: "#how-it-works", labelKey: "marketing.nav.howItWorks" },
  { href: "#safeguards", labelKey: "marketing.nav.safeguards" },
  { href: "#agents", labelKey: "marketing.nav.agents" },
  { href: "#faq", labelKey: "marketing.nav.faq" },
];

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
        scrolled ? "glass-surface border-b border-line/60 shadow-card" : ""
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link href="/" className="flex items-center gap-2">
          <WingMark size={22} className="text-primary" />
          <span className="text-[15px] font-bold tracking-tight">SEPHIROTH</span>
        </Link>

        <nav className="hidden items-center gap-6 text-sm font-medium text-muted md:flex">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} className="link-underline">
              {t(link.labelKey)}
            </a>
          ))}
        </nav>

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

      {/* An action sheet rather than a side drawer: these are jumps within one
          page, not navigation into a section of an app. */}
      <Sheet open={menuOpen} onClose={() => setMenuOpen(false)} side="bottom" title={t("nav.menu")}>
        <nav className="flex flex-col gap-1">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              className="nav-item tap"
            >
              {t(link.labelKey)}
            </a>
          ))}
        </nav>
        <div className="mt-4 flex justify-center border-t border-line/60 pt-4">
          <ThemeToggle />
        </div>
      </Sheet>
    </header>
  );
}
