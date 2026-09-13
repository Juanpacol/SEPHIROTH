/** Guards the one thing that would silently desynchronise /schedule's two
 * views: how an appointment's timestamp is turned into a wall-clock time.
 *
 * Appointment timestamps arrive naive and are read as UTC on purpose (see
 * `components/schedule/time.ts`). Reformatting one with plain
 * `new Date(iso)` instead would shift it by the browser's offset — so the week
 * grid and the day agenda would place the same appointment at different times,
 * and on a UTC machine every test would still pass.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Appointment } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";
import DayAgenda from "../day-agenda";
import { minutesFromDayStart, slotTime, START_HOUR } from "../time";

const APPOINTMENT: Appointment = {
  id: "ap-1",
  clinician_id: "u-1",
  patient_id: "p-1",
  patient_name: "María Fernanda Restrepo",
  start_at: "2026-01-12T14:30:00",
  end_at: "2026-01-12T15:00:00",
  status: "booked",
  mode: "in_person",
  reason: "Renal function review",
  cancellation_reason: "",
  series_id: null,
  confirmed_at: null,
};

describe("schedule time convention", () => {
  it("reads a naive timestamp as the wall-clock time the server meant", () => {
    // Not `expect(slotTime(...)).toBe(format(new Date(...)))` — that tautology
    // passes under any convention. The literal is the point.
    expect(slotTime(APPOINTMENT.start_at)).toBe("14:30");
    expect(slotTime(APPOINTMENT.end_at)).toBe("15:00");
  });

  it("places the same appointment consistently in both views", () => {
    const minutes = minutesFromDayStart(APPOINTMENT.start_at);
    const [hours, mins] = slotTime(APPOINTMENT.start_at).split(":").map(Number);
    // The grid's vertical offset and the agenda's printed time have to be two
    // readings of one timestamp, not two independent calculations.
    expect(minutes).toBe(hours * 60 + mins - START_HOUR * 60);
  });

  it("prints that same time in the agenda", () => {
    render(
      <LanguageProvider>
        <DayAgenda
          day={new Date(2026, 0, 12)}
          appointments={[APPOINTMENT]}
          onRequestCancel={() => {}}
          onBook={() => {}}
        />
      </LanguageProvider>,
    );
    expect(screen.getByText("14:30")).toBeInTheDocument();
    expect(screen.getByText(APPOINTMENT.patient_name!)).toBeInTheDocument();
  });
});
