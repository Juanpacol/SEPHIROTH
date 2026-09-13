"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, differenceInCalendarDays, format, isSameDay, startOfWeek } from "date-fns";
import { CalendarClock } from "lucide-react";
import { api, ApiError, type Appointment } from "@/lib/api";
import { useUser } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import AvailabilitySheet from "@/components/schedule/availability-sheet";
import BookAppointmentSheet from "@/components/schedule/book-appointment-sheet";
import DayAgenda from "@/components/schedule/day-agenda";
import DayStrip from "@/components/schedule/day-strip";
import WeekGrid from "@/components/schedule/week-grid";
import Dialog from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";

export default function SchedulePage() {
  const user = useUser();
  const { t } = useLanguage();
  const queryClient = useQueryClient();
  const showToast = useToast();
  const [anchor, setAnchor] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));
  const [availabilityOpen, setAvailabilityOpen] = useState(false);
  const [bookOpen, setBookOpen] = useState(false);
  const [bookDate, setBookDate] = useState(format(new Date(), "yyyy-MM-dd"));
  // Confirmation lives here, once, for both views. It used to be a native
  // `window.confirm` inside the grid: that blocks the main thread, cannot be
  // styled or translated, and on a phone throws the user out of the app's
  // chrome entirely.
  const [pendingCancel, setPendingCancel] = useState<Appointment | null>(null);

  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(anchor, i)), [anchor]);
  // Which day the phone agenda shows. Stored as an offset into the visible week
  // rather than as a Date, so paging the week can never leave it pointing at a
  // day that is no longer on screen — and paging keeps the weekday you were on.
  //
  // Opens on today, not on Monday: the first thing a clinician wants from a
  // schedule on their phone is what is left of today.
  const [dayOffset, setDayOffset] = useState(() =>
    differenceInCalendarDays(new Date(), startOfWeek(new Date(), { weekStartsOn: 1 })),
  );
  const selectedDay = days[dayOffset] ?? days[0];
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
              className="btn-ghost tap px-2.5 py-1.5"
              aria-label={t("schedule.previousWeek")}
            >
              ‹
            </button>
            <button
              onClick={() => setAnchor(startOfWeek(new Date(), { weekStartsOn: 1 }))}
              className="btn-ghost tap px-2.5 py-1.5 text-sm"
            >
              {t("schedule.today")}
            </button>
            <button
              onClick={() => setAnchor(addDays(anchor, 7))}
              className="btn-ghost tap px-2.5 py-1.5"
              aria-label={t("schedule.nextWeek")}
            >
              ›
            </button>
          </div>
          <span className="text-sm text-muted">
            {format(anchor, "MMM d")} – {format(addDays(anchor, 6), "MMM d, yyyy")}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => setAvailabilityOpen(true)} className="btn-secondary tap flex-1 sm:flex-none">
            <CalendarClock size={16} /> {t("schedule.workingHours")}
          </button>
          <button
            onClick={() => {
              setBookDate(format(new Date(), "yyyy-MM-dd"));
              setBookOpen(true);
            }}
            className="btn-primary tap flex-1 sm:flex-none"
          >
            {t("schedule.newAppointment")}
          </button>
        </div>
      </div>

      {/* Phone: a day at a time. Tablet and up: the week grid. Both are fed by
          the same weekly query — switching views costs no extra fetch. */}
      <div className="space-y-4 md:hidden">
        <DayStrip
          days={days}
          selected={selectedDay}
          onSelect={(day) => setDayOffset(days.findIndex((d) => isSameDay(d, day)))}
          countFor={(day) => (appointmentsByDay.get(format(day, "yyyy-MM-dd")) ?? []).length}
        />
        <DayAgenda
          day={selectedDay}
          appointments={appointmentsByDay.get(format(selectedDay, "yyyy-MM-dd")) ?? []}
          onRequestCancel={setPendingCancel}
          onBook={(dayIso) => {
            setBookDate(dayIso);
            setBookOpen(true);
          }}
        />
      </div>

      <div className="card hidden overflow-x-auto p-0 md:block">
        <WeekGrid days={days} appointmentsByDay={appointmentsByDay} onRequestCancel={setPendingCancel} />
      </div>

      {(!availability || availability.rules.length === 0) && (
        <div className="card">
          <p className="text-sm font-semibold">{t("schedule.setHoursPrompt")}</p>
          <button onClick={() => setAvailabilityOpen(true)} className="btn-primary mt-3">
            {t("schedule.setWorkingHours")}
          </button>
        </div>
      )}

      <Dialog
        open={pendingCancel !== null}
        onClose={() => setPendingCancel(null)}
        title={t("schedule.confirmCancel").replace(
          "{name}",
          pendingCancel?.patient_name ?? t("schedule.patientFallback"),
        )}
        confirmLabel={t("schedule.agenda.cancel")}
        destructive
        onConfirm={() => {
          if (pendingCancel) cancel(pendingCancel.id);
          setPendingCancel(null);
        }}
      />

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
