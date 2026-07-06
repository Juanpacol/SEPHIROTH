"use client";

import { usePathname } from "next/navigation";
import Sidebar from "@/components/sidebar";
import Topbar from "@/components/topbar";

/** Full dashboard chrome, except on auth pages which render bare. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/login") return <>{children}</>;

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 p-6">{children}</main>
        <footer className="px-6 pb-4 text-center text-xs text-muted">
          Decision support only — not a medical device. All AI output requires professional
          review.
        </footer>
      </div>
    </div>
  );
}
