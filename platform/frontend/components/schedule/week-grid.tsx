"use client";

/** The seven-day timetable — the desktop half of /schedule.
 *
 * Lifted out of the page unchanged, including its `min-w-[900px]` and the
 * `overflow-x-auto` wrapper the page keeps around it. Seven columns genuinely
 * need that width; the answer for a phone is `day-agenda.tsx`, not a narrower
 * grid, so this one is free to stay wide. */

import { useEffect, useRef, useState } from "react";
import { format } from "date-fns";
import type { Appointment } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import {
  durationMinutes,
  minutesFromDayStart,
  slotTime,
  ROW_HEIGHT_REM,
  ROW_MINUTES,
  ROWS,
  START_HOUR,
} from "./time";

/** The current time, refreshed once a minute, for the line that marks it on today's column. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);
  return now;
}

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
  const now = useNow();
  const todayKey = format(now, "yyyy-MM-dd");
  const todayIndex = days.findIndex((day) => format(day, "yyyy-MM-dd") === todayKey);
  // Minutes since the grid opens; the line is drawn only while it is inside the grid's hours.
  const nowMinutes = now.getHours() * 60 + now.getMinutes() - START_HOUR * 60;
  const nowRef = useRef<HTMLDivElement>(null);
  const showNow = todayIndex >= 0 && nowMinutes >= 0 && nowMinutes <= ROWS * ROW_MINUTES;

  // Opening on this week, bring the present hour into view once: the grid starts at the first working hour.
  const scrolled = useRef(false);
  useEffect(() => {
    if (scrolled.current || !nowRef.current) return;
    scrolled.current = true;
    nowRef.current.scrollIntoView({ block: "center" });
  });

  return (
    <div className="min-w-[900px]">
      <div className="grid grid-cols-[4.5rem_repeat(7,1fr)]">
        <div className="border-b border-line/50" />
        {days.map((day) => {
          const isToday = format(day, "yyyy-MM-dd") === todayKey;
          return (
            <div key={day.toISOString()} className="border-b border-l border-line/50 px-2 py-2.5 text-center">
              <div className={`eyebrow ${isToday ? "text-primary-ink" : "text-muted"}`}>
                {format(day, "EEE")}
              </div>
              <div
                className={`mx-auto mt-1 font-display text-2xl font-light leading-none ${
                  isToday ? "text-primary-ink" : "text-ink"
                }`}
              >
                {format(day, "d")}
              </div>
              <div
                aria-hidden
                className={`mx-auto mt-1.5 h-px w-6 bg-primary-ink transition-transform duration-300 ${
                  isToday ? "scale-x-100" : "scale-x-0"
                }`}
              />
            </div>
          );
        })}
      </div>

      <div className="relative grid grid-cols-[4.5rem_repeat(7,1fr)]">
        {showNow && (
          <div
            ref={nowRef}
            aria-hidden
            className="pointer-events-none absolute z-20"
            style={{
              top: `${(nowMinutes / ROW_MINUTES) * ROW_HEIGHT_REM}rem`,
              left: `calc(4.5rem + ${todayIndex} * (100% - 4.5rem) / 7)`,
              width: "calc((100% - 4.5rem) / 7)",
            }}
          >
            <div className="relative h-px bg-danger">
              <span className="absolute -left-1 -top-[3px] h-[7px] w-[7px] rounded-full bg-danger" />
            </div>
          </div>
        )}
        {Array.from({ length: ROWS }, (_, row) => {
          const totalMinutes = START_HOUR * 60 + row * ROW_MINUTES;
          const hour = Math.floor(totalMinutes / 60);
          const minute = totalMinutes % 60;
          return (
            <div key={row} className="contents">
              <div
                className="border-b border-line/30 pr-2 pt-0.5 text-right font-mono text-[10px] tracking-wide text-muted"
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
                    className="relative border-b border-l border-line/30 transition-colors duration-normal hover:bg-primary-soft/20"
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
                          className={`absolute inset-x-0.5 top-0 z-10 overflow-hidden rounded-lg border-l-2 px-1.5 py-0.5 text-left text-[11px] transition-colors duration-normal ${
                            appt.status === "completed"
                              ? "border-success bg-success/15 text-ink hover:bg-success/25"
                              : "border-primary-ink bg-primary-ink/15 text-ink hover:bg-primary-ink/25"
                          }`}
                          style={{ height: `${heightRem}rem` }}
                          title={`${name} — ${appt.reason || t("schedule.noReason")}`}
                        >
                          <span className="block font-mono text-[10px] text-muted">
                            {slotTime(appt.start_at)}
                          </span>
                          <span className="block truncate font-semibold">{name}</span>
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
    </div>
  );
}
