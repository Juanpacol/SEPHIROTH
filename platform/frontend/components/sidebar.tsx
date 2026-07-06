"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BookOpenCheck,
  Bot,
  LayoutDashboard,
  ScanEye,
  Search,
  Users,
} from "lucide-react";

const groups = [
  {
    label: null,
    items: [{ href: "/dashboard", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Clinical",
    items: [
      { href: "/copilot", label: "Copilot Chat", icon: Bot },
      { href: "/patients", label: "Patients", icon: Users },
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

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line/60 bg-card px-3 py-5 md:flex">
      <Link href="/dashboard" className="flex items-center gap-2 px-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-sephiroth font-extrabold text-ink/80">
          S
        </span>
        <span className="text-[15px] font-bold tracking-tight">SEPHIROTH</span>
      </Link>

      <div className="mt-5 flex items-center gap-2 rounded-xl border border-line/70 px-3 py-2 text-sm text-muted">
        <Search size={15} />
        <span>Search</span>
      </div>

      <nav className="mt-2 flex-1">
        {groups.map((group) => (
          <div key={group.label ?? "root"}>
            {group.label && <div className="nav-group-label">{group.label}</div>}
            {group.items.map(({ href, label, icon: Icon }) => {
              const active = pathname.startsWith(href);
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

      <div className="rounded-xl bg-sephiroth p-3 text-xs font-medium text-ink/80">
        100% local inference
        <div className="mt-0.5 font-normal text-ink/60">Ollama · qwen3:8b</div>
      </div>
    </aside>
  );
}
