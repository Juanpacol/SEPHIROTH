"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { clearAuth, useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import { flatNav, isActive, navFor } from "@/lib/nav";
import { useBadgeCounts } from "@/lib/hooks/use-badge-counts";
import WingMark from "@/components/brand/wing-mark";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = useUser();
  const { t } = useLanguage();
  const groups = navFor(user?.role);
  const allHrefs = flatNav(groups).map((i) => i.href);
  const { data: counts } = useBadgeCounts();
  const homeHref = user?.role === "patient" ? "/portal" : "/work";
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

      <nav className="mt-2 flex-1">
        {groups.map((group) => (
          <div key={group.groupId ?? "root"}>
            {group.groupId && <div className="nav-group-label">{t(`nav.${group.groupId}`)}</div>}
            {group.items.map(({ href, id, icon: Icon, badge }) => {
              const active = isActive(pathname, href, allHrefs);
              const count = badge ? (counts?.[badge] ?? 0) : 0;
              return (
                <Link key={href} href={href} className={`nav-item ${active ? "nav-item-active" : ""}`}>
                  <Icon size={17} />
                  <span className="flex-1">{t(`nav.${id}`)}</span>
                  {count > 0 && (
                    <span className="rounded-full bg-primary px-1.5 text-[11px] font-bold text-white">
                      {count > 99 ? "99+" : count}
                    </span>
                  )}
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
            <div className="truncate font-semibold">{user?.name ?? t("nav.notSignedIn")}</div>
            <div className="text-xs text-muted">
              {user ? t(user.role === "patient" ? "nav.rolePatient" : "nav.roleClinician") : ""}
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
