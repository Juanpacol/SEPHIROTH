"use client";

/** The desktop navigation rail. Hidden below `md:`, where
 * `components/mobile-tab-bar.tsx` and `components/mobile-nav-drawer.tsx` take
 * over — all three read their destinations from `lib/nav.ts`. */

import Link from "next/link";
import { Search } from "lucide-react";
import { homeFor, useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import NavLinks from "@/components/nav-links";
import NavUserCard from "@/components/nav-user-card";
import WingMark from "@/components/brand/wing-mark";
import Wordmark from "@/components/landing/wordmark";

export default function Sidebar() {
  const user = useUser();
  const { t } = useLanguage();

  return (
    <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line/40 px-3 py-5 md:flex">
      <Link
        href={user ? homeFor(user.role) : "/dashboard"}
        className="group/brand flex items-center gap-2.5 px-3"
      >
        <WingMark size={20} className="text-primary-ink" />
        <Wordmark className="text-[21px] tracking-[0.16em]" />
      </Link>

      {user?.role !== "patient" && (
        <div className="mt-6 flex items-center gap-2.5 border-b border-line/60 px-3 pb-2.5 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          <Search size={14} strokeWidth={1.5} />
          <span>{t("nav.search")}</span>
        </div>
      )}

      <NavLinks className="mt-1 flex-1" />

      <NavUserCard />
    </aside>
  );
}
