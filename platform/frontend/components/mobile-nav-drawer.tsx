"use client";

/** Everything the tab bar has no room for, plus the account row and the theme
 * toggle. Opened by the hamburger in `components/topbar.tsx`. */

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/lib/language";
import Sheet from "@/components/ui/sheet";
import NavLinks from "@/components/nav-links";
import NavUserCard from "@/components/nav-user-card";
import ThemeToggle from "@/components/theme-toggle";

export default function MobileNavDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { t } = useLanguage();

  // Close on navigation. Tapping a link inside the drawer also calls
  // `onNavigate` below; this covers the rest — a back gesture, a redirect.
  useEffect(() => {
    onClose();
    // Deliberately keyed on pathname alone: re-running because `onClose`
    // changed identity would slam the drawer shut as it opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  return (
    <Sheet open={open} onClose={onClose} side="left" title={t("nav.menu")}>
      <div className="flex h-full flex-col">
        <NavLinks className="flex-1" onNavigate={onClose} />
        <div className="flex justify-end pb-3">
          <ThemeToggle />
        </div>
        <NavUserCard onNavigate={onClose} />
      </div>
    </Sheet>
  );
}
