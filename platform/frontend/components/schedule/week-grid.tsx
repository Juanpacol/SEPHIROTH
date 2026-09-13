"use client";

/** The seven-day timetable — the desktop half of /schedule.
 *
 * Lifted out of the page unchanged, including its `min-w-[900px]` and the
 * `overflow-x-auto` wrapper the page keeps around it. Seven columns genuinely
 * need that width; the answer for a phone is `day-agenda.tsx`, not a narrower
 * grid, so this one is free to stay wide. */

import { format } from "date-fns";
import type { Appointment } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import {
  durationMinutes,
  minutesFromDayStart,
  ROW_HEIGHT_REM,
  ROW_MINUTES,
  ROWS,
  START_HOUR,
} from "./time";

export default function WeekGrid({
  days,
  appointmentsByDay,
  onRequestCancel,
}: {
  days: Date[];
  appointmentsByDay: Map<string, Appointment[]>;
  /** Raises the appointment for the page to confirm — this component does not
   * decide how a confirmation looks. */
  onRequestCancel: (appointment: Appointment) => void;
}) {
  const { t } = useLanguage();
  const todayKey = format(new Date(), "yyyy-MM-dd");

  return (
    <div className="grid min-w-[900px] grid-cols-[4.5rem_repeat(7,1fr)]">
      <div className="border-b border-line/60" />
      {days.map((day) => (
        <div key={day.toISOString()} className="border-b border-l border-line/60 px-2 py-2 text-center">
          <div className="text-xs font-semibold uppercase text-muted">{format(day, "EEE")}</div>
          <div
            className={`mx-auto mt-0.5 flex h-6 w-6 items-center justify-center rounded-full text-sm font-bold ${
              format(day, "yyyy-MM-dd") === todayKey ? "bg-primary text-white" : ""
            }`}
          >
            {format(day, "d")}
          </div>
        </div>
      ))}

      {Array.from({ length: ROWS }, (_, row) => {
        const totalMinutes = START_HOUR * 60 + row * ROW_MINUTES;
        const hour = Math.floor(totalMinutes / 60);
        const minute = totalMinutes % 60;
        return (
          <div key={row} className="contents">
            <div
              className="border-b border-line/40 pr-2 text-right text-[11px] text-muted"
              style={{ height: `${ROW_HEIGHT_REM}rem` }}
            >
              {minute === 0 ? `${hour}:00` : ""}
            </div>
            {days.map((day) => {
              const dayKey = format(day, "yyyy-MM-dd");
              const dayAppointments = (appointmentsByDay.get(dayKey) ?? []).filter((appt) => {
                const m = minutesFromDayStart(appt.start_at);
                return m >= row * ROW_MINUTES && m < (row + 1) * ROW_MINUTES;
              });
              return (
                <div
                  key={dayKey + row}
                  className="relative border-b border-l border-line/40"
                  style={{ height: `${ROW_HEIGHT_REM}rem` }}
                >
                  {dayAppointments.map((appt) => {
                    const heightRem =
                      (durationMinutes(appt.start_at, appt.end_at) / ROW_MINUTES) * ROW_HEIGHT_REM;
                    const name = appt.patient_name ?? t("schedule.patientFallback");
                    return (
                      <button
                        key={appt.id}
                        onClick={() => {
                          if (appt.status === "booked") onRequestCancel(appt);
                        }}
                        className={`absolute inset-x-0.5 top-0 z-10 overflow-hidden rounded-lg px-1.5 py-0.5 text-left text-[11px] font-semibold text-white shadow-sm ${
                          appt.status === "completed" ? "bg-success" : "bg-primary"
                        }`}
                        style={{ height: `${heightRem}rem` }}
                        title={`${name} — ${appt.reason || t("schedule.noReason")}`}
                      >
                        {name}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
