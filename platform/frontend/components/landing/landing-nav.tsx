"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import WingMark from "@/components/brand/wing-mark";
import ThemeToggle from "@/components/theme-toggle";
import { ShimmerButton } from "@/components/magicui/shimmer-button";

const LINKS = [
  { href: "#how-it-works", label: "How it works" },
  { href: "#safeguards", label: "Safeguards" },
  { href: "#agents", label: "Agents" },
  { href: "#faq", label: "FAQ" },
];

export default function LandingNav() {
  const [scrolled, setScrolled] = useState(false);

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
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          <ShimmerButton href="/login" className="!px-4 !py-2 !text-sm">
            Open the app
          </ShimmerButton>
        </div>
      </div>
    </header>
  );
}
