"use client";

/** The phone's primary navigation: a fixed bottom bar, plus a drawer for
 * everything that does not fit in it.
 *
 * Until this existed the app had no navigation at all below `md` — the sidebar
 * is `hidden md:flex` with nothing in its place, so a clinician on a phone
 * could reach exactly the page they landed on. A bottom bar rather than a
 * hamburger because these are the destinations someone switches between all
 * day, and the bottom of the screen is where a thumb already is.
 *
 * Four destinations plus "More": a fifth destination would push each target
 * under the 44px comfortable minimum on a 375px screen. Which four is decided
 * by `mobile: true` in `lib/nav.ts`, next to the destinations themselves. */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LogOut, MoreHorizontal } from "lucide-react";
import { clearAuth, useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import { flatNav, isActive, navFor } from "@/lib/nav";
import Sheet from "@/components/ui/sheet";

export default function MobileNav() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useUser();
  const { t } = useLanguage();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const groups = navFor(user?.role);
  const items = flatNav(groups);
  const allHrefs = items.map((i) => i.href);
  const barItems = items.filter((i) => i.mobile);
  const overflow = items.filter((i) => !i.mobile);

  // A navigation drawer that survives navigation is a drawer covering the page
  // it just opened.
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  const logout = () => {
    clearAuth();
    router.push("/login");
  };

  return (
    <>
      <nav
        aria-label={t("nav.primary")}
        className="glass-surface safe-bottom fixed inset-x-0 bottom-0 z-40 flex border-t border-line/60 md:hidden"
      >
        {barItems.map(({ href, id, icon: Icon }) => {
          const active = isActive(pathname, href, allHrefs);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`flex h-16 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-semibold transition-colors ${
                active ? "text-primary" : "text-ink/60"
              }`}
            >
              <Icon size={20} />
              <span className="max-w-full truncate px-1">{t(`nav.${id}`)}</span>
            </Link>
          );
        })}

        {overflow.length > 0 && (
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-expanded={drawerOpen}
            className="flex h-16 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-semibold text-ink/60"
          >
            <MoreHorizontal size={20} />
            <span>{t("common.more")}</span>
          </button>
        )}
      </nav>

      <Sheet open={drawerOpen} onClose={() => setDrawerOpen(false)} title={t("common.menu")} side="bottom">
        <div className="flex flex-col gap-1">
          {overflow.map(({ href, id, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`nav-item ${isActive(pathname, href, allHrefs) ? "nav-item-active" : ""}`}
            >
              <Icon size={17} />
              {t(`nav.${id}`)}
            </Link>
          ))}
          {user && (
            <button type="button" onClick={logout} className="nav-item text-danger hover:text-danger">
              <LogOut size={17} />
              {t("nav.logout")}
            </button>
          )}
        </div>
      </Sheet>
    </>
  );
}
