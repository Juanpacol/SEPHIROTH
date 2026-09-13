"use client";

/** The signed-in user's row plus sign-out — the foot of both the desktop
 * sidebar and the mobile drawer. Extracted rather than duplicated because the
 * two would drift the moment the row gains anything (an org name, a status). */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { clearAuth, useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";

/** "Dr. Ana María Ruiz" → "AM". The honorific is dropped so two clinicians who
 * share one don't end up with the same initials. */
function initialsFor(name: string): string {
  return name
    .split(" ")
    .filter((w) => w && w !== "Dr." && w !== "Dr")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export default function NavUserCard({ onNavigate }: { onNavigate?: () => void }) {
  const router = useRouter();
  const user = useUser();
  const { t } = useLanguage();
  const profileHref = user?.role === "patient" ? "/portal" : "/profile";

  const logout = () => {
    clearAuth();
    router.push("/login");
  };

  return (
    <div className="flex items-center gap-2 border-t border-line/60 px-1 pt-3">
      <Link
        href={profileHref}
        onClick={onNavigate}
        className="tap flex min-w-0 flex-1 items-center gap-2.5 rounded-2xl px-2 py-1.5 hover:bg-primary-soft"
      >
        <div className="ai-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-bold text-primary">
          {user ? initialsFor(user.name) : "…"}
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
          className="tap shrink-0 rounded-full p-2 text-muted hover:bg-primary-soft hover:text-danger"
          aria-label={t("nav.logout")}
          title={t("nav.logout")}
        >
          <LogOut size={17} />
        </button>
      )}
    </div>
  );
}
