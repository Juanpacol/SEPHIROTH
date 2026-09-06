"use client";

/** Today's appointments, on the page a clinician opens first.
 *
 * `/api/dashboard/bootstrap` has always returned this. The old dashboard
 * fetched it and rendered none of it — a clinician had to go to a second page
 * to answer "who am I seeing next", which is the first question of the day.
 *
 * The "next in N minutes" line is computed client-side from `next_at` rather
 * than asked of the server, because a countdown that only updates on a 30-second
 * poll is a countdown that is wrong most of the time.
 */

import Link from "next/link";
import { CalendarDays } from "lucide-react";
import type { TodayAgenda } from "@/lib/api";
import { useLanguage } from "@/lib/language";

const MAX_ROWS = 4;

function minutesUntil(iso: string): number {
  return Math.round((new Date(iso).getTime() - Date.now()) / 60_000);
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function AgendaTodayCard({ agenda }: { agenda?: TodayAgenda }) {
  const { t } = useLanguage();

  const nextLine = (() => {
    if (!agenda?.next_at) return null;
    const mins = minutesUntil(agenda.next_at);
    if (mins < 0) return t("work.agenda.inProgress");
    if (mins < 60) return t("work.agenda.nextInMinutes", { minutes: String(mins) });
    return t("work.agenda.nextAt", { time: timeLabel(agenda.next_at) });
  })();

  return (
    <div className="card !p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-bold">
          <CalendarDays size={15} className="text-primary" /> {t("work.agenda.title")}
        </h2>
        <Link href="/agenda" className="text-xs font-semibold text-primary">
          {t("work.viewAll")}
        </Link>
      </div>

      {nextLine && <p className="mb-2 text-sm font-semibold text-primary">{nextLine}</p>}

      {!agenda || agenda.count === 0 ? (
        <p className="text-sm text-muted">{t("work.agenda.empty")}</p>
      ) : (
        <ul className="divide-y divide-line/40">
          {agenda.items.slice(0, MAX_ROWS).map((item) => (
            <li key={item.id} className="flex items-baseline gap-3 py-2 text-sm">
              <span className="w-12 shrink-0 font-semibold tabular-nums">{timeLabel(item.start_at)}</span>
              <span className="min-w-0 flex-1 truncate">{item.patient_name}</span>
              {item.reason && <span className="hidden truncate text-xs text-muted sm:block">{item.reason}</span>}
            </li>
          ))}
        </ul>
      )}

      {agenda && agenda.count > MAX_ROWS && (
        <p className="mt-2 text-xs text-muted">
          {t("work.agenda.more", { count: String(agenda.count - MAX_ROWS) })}
        </p>
      )}
    </div>
  );
}
