"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CalendarClock, ChevronRight } from "lucide-react";
import { useUser } from "@/lib/auth";
import NotificationBell from "@/components/notification-bell";
import ThemeToggle from "@/components/theme-toggle";

export default function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useUser();
  const crumbs = pathname.split("/").filter(Boolean);

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
      className={`glass-surface sticky top-0 z-10 flex items-center justify-between border-b border-line/60 px-6 transition-all duration-200 ${
        scrolled ? "py-2.5 shadow-card" : "py-3.5"
      }`}
    >
      <nav className="flex items-center gap-1.5 text-sm capitalize text-muted">
        {crumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight size={14} />}
            <span className={i === crumbs.length - 1 ? "font-semibold text-ink" : ""}>
              {decodeURIComponent(crumb)}
            </span>
          </span>
        ))}
      </nav>

      <div className="flex items-center gap-4">
        <ThemeToggle />
        {user?.role !== "patient" && (
          <button
            onClick={() => router.push("/schedule")}
            className="rounded-full p-2 text-muted hover:bg-primary-soft"
            aria-label="Schedule"
          >
            <CalendarClock size={18} />
          </button>
        )}
        <NotificationBell />
      </div>
    </header>
  );
}
