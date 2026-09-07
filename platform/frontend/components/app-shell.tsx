"use client";

import { usePathname } from "next/navigation";
import AuthGuard from "@/components/auth-guard";
import Sidebar from "@/components/sidebar";
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
          <main className="flex-1 p-6">{children}</main>
          <footer className="px-6 pb-4 text-center text-xs text-muted">{t("common.footerDisclaimer")}</footer>
        </div>
      </div>
      <CopilotWidget />
    </AuthGuard>
  );
}
