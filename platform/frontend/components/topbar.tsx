"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CalendarClock, ChevronRight, Menu } from "lucide-react";
import { useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import { CLINICIAN_NAV, PATIENT_NAV } from "@/lib/nav";
import MobileNavDrawer from "@/components/mobile-nav-drawer";
import NotificationBell from "@/components/notification-bell";
import ThemeToggle from "@/components/theme-toggle";

const NAV_ID_BY_HREF = new Map(
  [...CLINICIAN_NAV, ...PATIENT_NAV].flatMap((group) => group.items.map((item) => [item.href, item.id] as const))
);

export default function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useUser();
  const { t } = useLanguage();
  const crumbs = pathname.split("/").filter(Boolean);
  const [menuOpen, setMenuOpen] = useState(false);

  // Aceternity "resizable navbar" behavior: the bar tightens and gains a
  // frosted-glass background once the page has scrolled, like iOS's
  // UINavigationBar large-title collapse.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`glass-surface sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-line/60 px-4 transition-all duration-200 md:px-6 ${
        scrolled ? "py-2.5 shadow-card" : "py-3.5"
      }`}
    >
      <div className="flex min-w-0 items-center gap-1">
        <button
          onClick={() => setMenuOpen(true)}
          className="tap -ml-2 shrink-0 rounded-full p-2 text-ink/70 hover:bg-primary-soft hover:text-primary md:hidden"
          aria-label={t("nav.menu")}
          aria-expanded={menuOpen}
          aria-controls="mobile-nav"
        >
          <Menu size={20} />
        </button>

        <nav className="flex min-w-0 items-center gap-1.5 text-sm capitalize text-muted">
          {crumbs.map((crumb, i) => {
            const last = i === crumbs.length - 1;
            return (
              // Intermediate crumbs are dropped on a phone: the last one is the
              // only part that says where you are, and on /patients/[id] it is
              // a UUID that pushes the whole bar sideways without `truncate`.
              <span key={i} className={`items-center gap-1.5 ${last ? "flex min-w-0" : "hidden sm:flex"}`}>
                {i > 0 && <ChevronRight size={14} className="hidden shrink-0 sm:block" />}
                <span className={last ? "truncate font-semibold text-ink" : ""}>
                  {crumbLabel(crumbs, i, t)}
                </span>
              </span>
            );
          })}
        </nav>
      </div>

      <div className="flex shrink-0 items-center gap-1 md:gap-4">
        <ThemeToggle className="hidden md:inline-flex" />
        {user?.role !== "patient" && (
          // Hidden on a phone — the tab bar already goes there.
          <button
            onClick={() => router.push("/schedule")}
            className="tap hidden rounded-full p-2 text-muted hover:bg-primary-soft sm:inline-flex sm:items-center sm:justify-center"
            aria-label={t("nav.schedule")}
          >
            <CalendarClock size={18} />
          </button>
        )}
        <NotificationBell />
      </div>

      <div id="mobile-nav">
        <MobileNavDrawer open={menuOpen} onClose={() => setMenuOpen(false)} />
      </div>
    </header>
  );
}

/** A route that is a nav destination reads with its nav label ("Panel", not
 * "dashboard"); anything else (an id, a sub-route) is shown as in the URL. */
function crumbLabel(crumbs: string[], i: number, t: (key: string) => string): string {
  const id = NAV_ID_BY_HREF.get(`/${crumbs.slice(0, i + 1).join("/")}`);
  return id ? t(`nav.${id}`) : decodeURIComponent(crumbs[i]);
}
