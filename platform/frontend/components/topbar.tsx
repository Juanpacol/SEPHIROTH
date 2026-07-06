"use client";

import { usePathname, useRouter } from "next/navigation";
import { Bell, CalendarClock, ChevronRight, LogOut } from "lucide-react";
import { clearAuth, useUser } from "@/lib/auth";

export default function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useUser();
  const crumbs = pathname.split("/").filter(Boolean);

  const initials = user
    ? user.name
        .split(" ")
        .filter((w) => w && w !== "Dr." && w !== "Dr")
        .map((w) => w[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "…";

  const logout = () => {
    clearAuth();
    router.push("/login");
  };

  return (
    <header className="flex items-center justify-between border-b border-line/60 bg-card px-6 py-3.5">
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
        <button className="rounded-full p-2 text-muted hover:bg-surface" aria-label="Schedule">
          <CalendarClock size={18} />
        </button>
        <button className="rounded-full p-2 text-muted hover:bg-surface" aria-label="Notifications">
          <Bell size={18} />
        </button>
        <div className="flex items-center gap-2.5">
          <div className="ai-ring flex h-9 w-9 items-center justify-center rounded-full bg-primary-soft text-sm font-bold text-primary">
            {initials}
          </div>
          <div className="hidden text-sm leading-tight sm:block">
            <div className="font-semibold">{user?.name ?? "Not signed in"}</div>
            <div className="text-xs text-muted">{user ? "Clinician" : ""}</div>
          </div>
        </div>
        {user && (
          <button
            onClick={logout}
            className="rounded-full p-2 text-muted hover:bg-surface hover:text-danger"
            aria-label="Log out"
            title="Log out"
          >
            <LogOut size={17} />
          </button>
        )}
      </div>
    </header>
  );
}
