"use client";

/** The primary navigation below `md:`, where the sidebar is hidden.
 *
 * Destinations come from `lib/nav.ts` (`primary: true`), never from a list of
 * its own — the drawer holds everything that doesn't fit here.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import { isActive, primaryTabs } from "@/lib/nav";

export default function MobileTabBar() {
  const pathname = usePathname();
  const user = useUser();
  const { t } = useLanguage();

  // Signed out, the only chrome-bearing routes are redirecting anyway.
  if (!user) return null;

  const tabs = primaryTabs(user.role);

  return (
    // The safe-area padding sits on the wrapper, outside `h-16`, so the usable
    // height stays exactly 4rem and `spacing.tabbar` (what `.pb-tabbar` clears)
    // keeps matching reality on a notched phone.
    // z-40: under sheets and toasts, over the sticky topbar.
    <div className="glass-surface fixed inset-x-0 bottom-0 z-40 border-t border-line/60 pb-[env(safe-area-inset-bottom)] md:hidden">
      <nav
        aria-label={t("nav.primary")}
        className="grid h-16"
        style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
      >
        {tabs.map(({ href, id, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={`tap flex flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-medium transition-colors ${
                active ? "text-primary" : "text-muted"
              }`}
            >
              <Icon size={20} />
              <span className="max-w-full truncate">{t(`nav.${id}`)}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
