"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BookOpenCheck,
  Bot,
  CalendarDays,
  ClipboardList,
  FileText,
  LayoutDashboard,
  ScanEye,
  Search,
  Users,
} from "lucide-react";
import { useUser } from "@/lib/auth";
import WingMark from "@/components/brand/wing-mark";

const CLINICIAN_NAV = [
  {
    label: null,
    items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Clinical",
    items: [
      { href: "/copilot", label: "Copilot Chat", icon: Bot },
      { href: "/patients", label: "Patients", icon: Users },
      { href: "/schedule", label: "Schedule", icon: CalendarDays },
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
  const user = useUser();
  const groups = user?.role === "patient" ? PATIENT_NAV : CLINICIAN_NAV;
  const homeHref = user?.role === "patient" ? "/portal" : "/dashboard";

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
          <span>Search</span>
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

      {user?.role !== "patient" && (
        <div className="rounded-2xl bg-sephiroth p-3 text-xs font-medium text-ink/80">
          100% local inference
          <div className="mt-0.5 font-normal text-ink/60">Gemini · 2.5 Flash</div>
        </div>
      )}
    </aside>
  );
}
