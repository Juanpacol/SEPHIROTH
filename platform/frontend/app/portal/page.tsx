"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";

/** Case-insensitive de-dup for display only — seed/demo data can carry the
 * same medication twice under slightly different casing or with/without a
 * dose (e.g. "metformin" and "Metformin 500mg"), which reads as two
 * different drugs to a patient. The underlying record is untouched. */
function uniqueByCasefold(items: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of items) {
    const key = item.trim().toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      result.push(item);
    }
  }
  return result;
}

export default function PortalHomePage() {
  const user = useUser();
  const { t } = useLanguage();

  const { data: me } = useQuery({ queryKey: ["portal", "me"], queryFn: api.portalMe });
  const { data: appointments } = useQuery({
    queryKey: ["portal", "appointments"],
    queryFn: () => api.listAppointments(),
  });
  const { data: shares } = useQuery({ queryKey: ["portal", "shares"], queryFn: () => api.listShares() });

  const upcoming = (appointments ?? []).filter((a) => a.status === "booked").slice(0, 1);
  const unreadResults = (shares ?? []).filter((s) => !s.viewed_at);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold">
          {t("portal.home.greeting").replace("{name}", user?.name?.split(" ")[0] ?? "")}
        </h1>
        {me && (
          <p className="text-sm text-muted">
            {t("portal.home.ageYears").replace("{name}", me.name).replace("{age}", String(me.age))}
          </p>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="card">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <CalendarDays size={16} className="text-primary" /> {t("portal.home.upcomingTitle")}
          </div>
          {upcoming.length === 0 && <p className="text-sm text-muted">{t("portal.home.noUpcoming")}</p>}
          <ul className="space-y-2">
            {upcoming.map((a) => (
              <li key={a.id} className="text-sm">
                <span className="font-semibold">
                  {new Date(a.start_at + "Z").toLocaleString([], {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
                {a.reason && <span className="text-muted"> — {a.reason}</span>}
              </li>
            ))}
          </ul>
          <Link href="/portal/appointments" className="mt-3 inline-block text-sm font-semibold text-primary">
            {t("portal.home.viewAllAppointments")}
          </Link>
        </div>

        <div className="card">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <FileText size={16} className="text-primary" /> {t("portal.home.resultsTitle")}
          </div>
          <p className="text-sm text-muted">
            {unreadResults.length === 0
              ? t("portal.home.noNewResults")
              : unreadResults.length === 1
                ? t("portal.home.newResult")
                : t("portal.home.newResults").replace("{count}", String(unreadResults.length))}
          </p>
          <Link href="/portal/results" className="mt-3 inline-block text-sm font-semibold text-primary">
            {t("portal.home.viewResults")}
          </Link>
        </div>
      </div>

      {me && (
        <div className="card">
          <div className="mb-3 text-sm font-semibold">{t("portal.home.summaryTitle")}</div>
          <div className="grid gap-4 text-sm sm:grid-cols-3">
            <div>
              <div className="text-xs font-semibold uppercase text-muted">{t("portal.home.conditions")}</div>
              <p>{me.conditions.length ? me.conditions.join(", ") : t("portal.home.noneOnFile")}</p>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase text-muted">{t("portal.home.medications")}</div>
              <p>
                {me.medications.length
                  ? uniqueByCasefold(me.medications).join(", ")
                  : t("portal.home.noneOnFile")}
              </p>
            </div>
            <div>
              <div className="text-xs font-semibold uppercase text-muted">{t("portal.home.allergies")}</div>
              <p>{me.allergies.length ? me.allergies.join(", ") : t("portal.home.noneOnFile")}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
