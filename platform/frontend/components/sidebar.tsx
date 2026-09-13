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

export default function Sidebar() {
  const user = useUser();
  const { t } = useLanguage();

  return (
    <aside className="glass-surface sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line/60 px-3 py-5 md:flex">
      <Link href={user ? homeFor(user.role) : "/dashboard"} className="flex items-center gap-2 px-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-2xl bg-primary-soft text-primary">
          <WingMark size={18} />
        </span>
        <span className="text-[15px] font-bold tracking-tight">SEPHIROTH</span>
      </Link>

      {user?.role !== "patient" && (
        <div className="mt-5 flex items-center gap-2 rounded-2xl border border-line/70 px-3 py-2 text-sm text-muted">
          <Search size={15} />
          <span>{t("nav.search")}</span>
        </div>
      )}

      <NavLinks className="mt-2 flex-1" />

      <NavUserCard />
    </aside>
  );
}
