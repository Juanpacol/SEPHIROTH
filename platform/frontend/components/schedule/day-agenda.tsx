"use client";

/** One day as a vertical list — the phone's replacement for the week grid.
 *
 * Not a narrower grid: a timetable's value is comparing columns, and there is
 * no useful comparison to make in 390px. A list of what is actually booked is,
 * so empty hours simply don't render.
 *
 * Times come from `./time`, the same helpers the week grid uses, so the two
 * views can never disagree about when an appointment is. */

import { format } from "date-fns";
import type { Appointment } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";
import { slotTime } from "./time";

export default function DayAgenda({
  day,
  appointments,
  onRequestCancel,
  onBook,
}: {
  day: Date;
  appointments: Appointment[];
  onRequestCancel: (appointment: Appointment) => void;
  onBook: (dayIso: string) => void;
}) {
  const { t } = useLanguage();
  const dayIso = format(day, "yyyy-MM-dd");
  const ordered = [...appointments].sort((a, b) => a.start_at.localeCompare(b.start_at));

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-bold">{format(day, "EEEE, MMMM d")}</h2>

      {ordered.length === 0 ? (
        <p className="card text-sm text-muted">{t("schedule.agenda.empty")}</p>
      ) : (
        <ul className="space-y-2">
          {ordered.map((appt) => {
            const name = appt.patient_name ?? t("schedule.patientFallback");
            return (
              <li key={appt.id} className="card flex gap-3 !p-4">
                {/* `tabular-nums` so the times line up as a column even though
                    each row lays itself out independently. */}
                <div className="shrink-0 text-sm font-bold tabular-nums text-primary">
                  {slotTime(appt.start_at)}
                  <span className="block text-xs font-medium text-muted">{slotTime(appt.end_at)}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="min-w-0 font-semibold">{name}</p>
                    <StatusPill label={appt.status.replace("_", " ")} />
                  </div>
                  <p className="text-xs text-muted">{appt.reason || t("schedule.noReason")}</p>
                  {appt.status === "booked" && (
                    <button
                      onClick={() => onRequestCancel(appt)}
                      className="tap mt-1 inline-flex items-center rounded-full text-xs font-semibold text-danger"
                    >
                      {t("schedule.agenda.cancel")}
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <button onClick={() => onBook(dayIso)} className="btn-secondary tap w-full">
        {t("schedule.agenda.bookOnDay")}
      </button>
    </div>
  );
}
