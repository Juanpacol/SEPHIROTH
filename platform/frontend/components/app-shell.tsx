"use client";

import { usePathname } from "next/navigation";
import AuthGuard from "@/components/auth-guard";
import Sidebar from "@/components/sidebar";
import MobileNav from "@/components/mobile-nav";
import Topbar from "@/components/topbar";
import CopilotWidget from "@/components/copilot/copilot-widget";
import { isChromelessRoute } from "@/lib/routes";
import { useLanguage } from "@/lib/language";

/** Full dashboard chrome, except on auth/public pages which render bare. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { t } = useLanguage();
  if (isChromelessRoute(pathname)) return <>{children}</>;

  return (
    <AuthGuard>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          {/* pb-24 clears the fixed bottom bar on a phone; without it the last
              row of every page sits under the navigation. */}
          <main className="flex-1 p-4 pb-24 md:p-6 md:pb-6">{children}</main>
          <footer className="px-4 pb-24 text-center text-xs text-muted md:px-6 md:pb-4">
            {t("common.footerDisclaimer")}
          </footer>
        </div>
      </div>
      <MobileNav />
      <CopilotWidget />
    </AuthGuard>
  );
}
