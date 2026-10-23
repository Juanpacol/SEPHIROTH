"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CalendarClock, Menu } from "lucide-react";
import { useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import { CLINICIAN_NAV, PATIENT_NAV } from "@/lib/nav";
import MobileNavDrawer from "@/components/mobile-nav-drawer";
import NotificationBell from "@/components/notification-bell";
import ThemeToggle from "@/components/theme-toggle";

const NAV_ID_BY_HREF = new Map(
  [...CLINICIAN_NAV, ...PATIENT_NAV].flatMap((group) =>
    group.items.map((item) => [item.href, item.id] as const)
  )
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
    <>
      <header
        className={`sticky top-0 z-10 flex items-center justify-between gap-2 border-b px-4 transition-[padding,background-color,border-color,backdrop-filter] duration-200 md:px-6 ${
          scrolled
            ? "border-line/50 bg-surface/70 py-2.5 backdrop-blur-md"
            : "border-transparent bg-transparent py-3.5"
        }`}
      >
        <div className="flex min-w-0 items-center gap-1">
          <button
            onClick={() => setMenuOpen(true)}
            className="icon-link tap -ml-2 shrink-0 md:hidden"
            aria-label={t("nav.menu")}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
          >
            <Menu size={20} strokeWidth={1.5} />
          </button>

          <nav className="flex min-w-0 items-center gap-2 font-mono text-[11px] uppercase tracking-[0.16em] text-muted">
            {crumbs.map((crumb, i) => {
              const last = i === crumbs.length - 1;
              return (
                // Intermediate crumbs are dropped on a phone: the last one is the
                // only part that says where you are, and on /patients/[id] it is
                // a UUID that pushes the whole bar sideways without `truncate`.
                <span key={i} className={`items-center gap-1.5 ${last ? "flex min-w-0" : "hidden sm:flex"}`}>
                  {i > 0 && (
                    <span aria-hidden className="hidden shrink-0 text-muted/50 sm:block">
                      /
                    </span>
                  )}
                  <span className={last ? "truncate font-semibold text-ink" : ""}>
                    {crumbLabel(crumbs, i, t)}
                  </span>
                </span>
              );
            })}
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-1 md:gap-4">
          <ThemeToggle bare className="hidden md:inline-flex" />
          {user?.role !== "patient" && (
            // Hidden on a phone — the tab bar already goes there.
            <button
              onClick={() => router.push("/schedule")}
              className="icon-link tap hidden sm:inline-flex"
              aria-label={t("nav.schedule")}
            >
              <CalendarClock size={18} strokeWidth={1.5} />
            </button>
          )}
          <NotificationBell />
        </div>
      </header>

      {/* Outside the header on purpose: the drawer is a fixed overlay with no
          width, but as a flex child `justify-between` still counted it and
          pushed the controls to the middle of the bar. */}
      <div id="mobile-nav">
        <MobileNavDrawer open={menuOpen} onClose={() => setMenuOpen(false)} />
      </div>
    </>
  );
}

/** A route that is a nav destination reads with its nav label ("Panel", not
 * "dashboard"); anything else (an id, a sub-route) is shown as in the URL. */
function crumbLabel(crumbs: string[], i: number, t: (key: string) => string): string {
  const id = NAV_ID_BY_HREF.get(`/${crumbs.slice(0, i + 1).join("/")}`);
  return id ? t(`nav.${id}`) : decodeURIComponent(crumbs[i]);
}
