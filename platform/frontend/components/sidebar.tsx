"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  BookOpenCheck,
  CalendarDays,
  CheckCircle2,
  ClipboardList,
  FileText,
  LayoutDashboard,
  LogOut,
  ScanEye,
  Search,
  Users,
} from "lucide-react";
import { clearAuth, useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import WingMark from "@/components/brand/wing-mark";

const CLINICIAN_NAV = [
  {
    label: null,
    items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Clinical",
    items: [
      { href: "/patients", label: "Patients", icon: Users },
      { href: "/schedule", label: "Schedule", icon: CalendarDays },
      { href: "/recommendations", label: "My Recommendations", icon: CheckCircle2 },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/imaging", label: "Imaging Analysis", icon: ScanEye },
      { href: "/evidence", label: "Evidence Library", icon: BookOpenCheck },
      { href: "/agents", label: "Agents Activity", icon: Activity },
    ],
  },
];

const PATIENT_NAV = [
  {
    label: null,
    items: [
      { href: "/portal", label: "My Health", icon: LayoutDashboard },
      { href: "/portal/appointments", label: "Appointments", icon: ClipboardList },
      { href: "/portal/results", label: "My Results", icon: FileText },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useUser();
  const { t } = useLanguage();
  const groups = user?.role === "patient" ? PATIENT_NAV : CLINICIAN_NAV;
  const homeHref = user?.role === "patient" ? "/portal" : "/dashboard";
  const profileHref = user?.role === "patient" ? "/portal" : "/profile";

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
    <aside className="glass-surface sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line/60 px-3 py-5 md:flex">
      <Link href={homeHref} className="flex items-center gap-2 px-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-2xl bg-primary-soft text-primary">
          <WingMark size={18} />
        </span>
        <span className="text-[15px] font-bold tracking-tight">SEPHIROTH</span>
      </Link>

      {user?.role !== "patient" && (
        <div className="mt-5 flex items-center gap-2 rounded-2xl border border-line/70 px-3 py-2 text-sm text-muted">
          <Search size={15} />
          <span>{t("nav.search")}</span>
        </div>
      )}

      <nav className="mt-2 flex-1">
        {groups.map((group) => (
          <div key={group.label ?? "root"}>
            {group.label && <div className="nav-group-label">{group.label}</div>}
            {group.items.map(({ href, label, icon: Icon }) => {
              const active = pathname === href || pathname.startsWith(href + "/");
              return (
                <Link
                  key={href}
                  href={href}
                  className={`nav-item ${active ? "nav-item-active" : ""}`}
                >
                  <Icon size={17} />
                  {label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="flex items-center gap-2 border-t border-line/60 px-1 pt-3">
        <Link href={profileHref} className="flex min-w-0 flex-1 items-center gap-2.5 rounded-2xl px-2 py-1.5 hover:bg-primary-soft">
          <div className="ai-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-bold text-primary">
            {initials}
          </div>
          <div className="min-w-0 text-sm leading-tight">
            <div className="truncate font-semibold">{user?.name ?? "Not signed in"}</div>
            <div className="text-xs text-muted">
              {user ? (user.role === "patient" ? "Patient" : "Clinician") : ""}
            </div>
          </div>
        </Link>
        {user && (
          <button
            onClick={logout}
            className="shrink-0 rounded-full p-2 text-muted hover:bg-primary-soft hover:text-danger"
            aria-label={t("nav.logout")}
            title={t("nav.logout")}
          >
            <LogOut size={17} />
          </button>
        )}
      </div>
    </aside>
  );
}
