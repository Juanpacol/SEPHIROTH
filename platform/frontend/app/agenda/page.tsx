"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format, startOfWeek } from "date-fns";
import { CalendarClock } from "lucide-react";
import { api, ApiError, type Appointment } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import AvailabilitySheet from "@/components/schedule/availability-sheet";
import BookAppointmentSheet from "@/components/schedule/book-appointment-sheet";
import { useToast } from "@/components/ui/toast";

const START_HOUR = 7;
const END_HOUR = 20;
const ROW_MINUTES = 30;
const ROW_HEIGHT_REM = 3;
const ROWS = ((END_HOUR - START_HOUR) * 60) / ROW_MINUTES;

function minutesFromDayStart(iso: string): number {
  const d = new Date(iso + "Z");
  return d.getUTCHours() * 60 + d.getUTCMinutes() - START_HOUR * 60;
}

export default function SchedulePage() {
  const user = useUser();
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const showToast = useToast();
  const [anchor, setAnchor] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));
  const [availabilityOpen, setAvailabilityOpen] = useState(false);
  const [bookOpen, setBookOpen] = useState(false);
  const [bookDate, setBookDate] = useState(format(new Date(), "yyyy-MM-dd"));

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(anchor, i)), [anchor]);
  const weekStartIso = format(anchor, "yyyy-MM-dd");
  const weekEndIso = format(addDays(anchor, 7), "yyyy-MM-dd");

  const { data: availability } = useQuery({
    queryKey: ["schedule", "availability"],
    queryFn: api.getAvailability,
  });

  const { data: appointments } = useQuery({
    queryKey: ["schedule", "appointments", weekStartIso, weekEndIso],
    queryFn: () => api.listAppointments({ from: `${weekStartIso}T00:00:00Z`, to: `${weekEndIso}T00:00:00Z` }),
  });

  const appointmentsByDay = useMemo(() => {
    const map = new Map<string, Appointment[]>();
    for (const appt of appointments ?? []) {
      if (appt.status === "cancelled") continue;
      const day = appt.start_at.slice(0, 10);
      map.set(day, [...(map.get(day) ?? []), appt]);
    }
    return map;
  }, [appointments]);

  const cancel = async (appointmentId: string) => {
    try {
      await api.cancelAppointment(appointmentId);
      await queryClient.invalidateQueries({ queryKey: ["schedule", "appointments"] });
      showToast(t("schedule.cancelled"));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("schedule.error.cancel"), "error");
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-bold">{t("nav.schedule")}</h1>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setAnchor(addDays(anchor, -7))}
              className="btn-ghost px-2.5 py-1.5"
              aria-label={t("schedule.previousWeek")}
            >
              ‹
            </button>
            <button
              onClick={() => setAnchor(startOfWeek(new Date(), { weekStartsOn: 1 }))}
              className="btn-ghost px-2.5 py-1.5 text-sm"
            >
              {t("schedule.today")}
            </button>
            <button
              onClick={() => setAnchor(addDays(anchor, 7))}
              className="btn-ghost px-2.5 py-1.5"
              aria-label={t("schedule.nextWeek")}
            >
              ›
            </button>
          </div>
          <span className="text-sm text-muted">
            {format(anchor, "MMM d")} – {format(addDays(anchor, 6), "MMM d, yyyy")}
          </span>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setAvailabilityOpen(true)} className="btn-secondary">
            <CalendarClock size={16} /> {t("schedule.workingHours")}
          </button>
          <button
            onClick={() => {
              setBookDate(format(new Date(), "yyyy-MM-dd"));
              setBookOpen(true);
            }}
            className="btn-primary"
          >
            {t("schedule.newAppointment")}
          </button>
        </div>
      </div>

      <div className="card overflow-x-auto p-0">
        <div className="grid min-w-[900px] grid-cols-[4.5rem_repeat(7,1fr)]">
          <div className="border-b border-line/60" />
          {days.map((day) => {
            const isToday = format(day, "yyyy-MM-dd") === format(new Date(), "yyyy-MM-dd");
            return (
              <div
                key={day.toISOString()}
                className="border-b border-l border-line/60 px-2 py-2 text-center"
              >
                <div className="text-xs font-semibold uppercase text-muted">{format(day, "EEE")}</div>
                <div
                  className={`mx-auto mt-0.5 flex h-6 w-6 items-center justify-center rounded-full text-sm font-bold ${
                    isToday ? "bg-primary text-white" : ""
                  }`}
                >
                  {format(day, "d")}
                </div>
              </div>
            );
          })}

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
                        const durationMin =
                          (new Date(appt.end_at + "Z").getTime() - new Date(appt.start_at + "Z").getTime()) /
                          60000;
                        const heightRem = (durationMin / ROW_MINUTES) * ROW_HEIGHT_REM;
                        return (
                          <button
                            key={appt.id}
                            onClick={() => {
                              const name = appt.patient_name ?? t("schedule.patientFallback");
                              if (
                                appt.status === "booked" &&
                                window.confirm(t("schedule.confirmCancel").replace("{name}", name))
                              )
                                cancel(appt.id);
                            }}
                            className={`absolute inset-x-0.5 top-0 z-10 overflow-hidden rounded-lg px-1.5 py-0.5 text-left text-[11px] font-semibold text-white shadow-sm ${
                              appt.status === "completed" ? "bg-success" : "bg-primary"
                            }`}
                            style={{ height: `${heightRem}rem` }}
                            title={`${appt.patient_name ?? t("schedule.patientFallback")} — ${
                              appt.reason || t("schedule.noReason")
                            }`}
                          >
                            {appt.patient_name ?? t("schedule.patientFallback")}
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

      {(!availability || availability.rules.length === 0) && (
        <div className="card">
          <p className="text-sm font-semibold">{t("schedule.setHoursPrompt")}</p>
          <button onClick={() => setAvailabilityOpen(true)} className="btn-primary mt-3">
            {t("schedule.setWorkingHours")}
          </button>
        </div>
      )}

      {user && (
        <AvailabilitySheet
          open={availabilityOpen}
          onClose={() => setAvailabilityOpen(false)}
          rules={availability?.rules ?? []}
        />
      )}
      {user && (
        <BookAppointmentSheet
          open={bookOpen}
          onClose={() => setBookOpen(false)}
          clinicianId={user.id}
          defaultDate={bookDate}
        />
      )}
    </div>
  );
}
