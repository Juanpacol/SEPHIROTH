"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Sheet from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type Slot } from "@/lib/api";

export default function BookAppointmentSheet({
  open,
  onClose,
  clinicianId,
  defaultDate,
}: {
  open: boolean;
  onClose: () => void;
  clinicianId: string;
  defaultDate: string; // yyyy-MM-dd
}) {
  const queryClient = useQueryClient();
  const showToast = useToast();
  const [date, setDate] = useState(defaultDate);
  const [patientId, setPatientId] = useState("");
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setDate(defaultDate);
      setSelectedSlot(null);
    }
  }, [open, defaultDate]);

  const { data: patients } = useQuery({ queryKey: ["patients"], queryFn: () => api.patients(), enabled: open });

  const nextDay = (d: string) => {
    const dt = new Date(`${d}T00:00:00`);
    dt.setDate(dt.getDate() + 1);
    return dt.toISOString().slice(0, 10);
  };

  const { data: slotsData } = useQuery({
    queryKey: ["schedule", "slots", clinicianId, date],
    queryFn: () => api.getSlots(clinicianId, date, nextDay(date)),
    enabled: open && !!date,
  });

  const book = async () => {
    if (!patientId || !selectedSlot) return;
    setBusy(true);
    try {
      await api.bookAppointment({
        clinician_id: clinicianId,
        patient_id: patientId,
        start_at: selectedSlot.start_at + "Z",
        reason,
      });
      await queryClient.invalidateQueries({ queryKey: ["schedule", "appointments"] });
      await queryClient.invalidateQueries({ queryKey: ["agenda", "today"] });
      showToast("Appointment booked.");
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        showToast("That time was just taken — pick another slot.", "error");
      } else if (err instanceof ApiError && err.status === 422) {
        showToast("That time is outside working hours.", "error");
      } else {
        showToast("Could not book this appointment.", "error");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="New appointment">
      <div className="space-y-4">
        <div>
          <label className="mb-1 block text-sm font-semibold">Patient</label>
          <select value={patientId} onChange={(e) => setPatientId(e.target.value)} className="input">
            <option value="">Select a patient…</option>
            {patients?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.medical_record_number})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm font-semibold">Date</label>
          <input
            type="date"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              setSelectedSlot(null);
            }}
            className="input"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-semibold">Time</label>
          <div className="flex flex-wrap gap-2">
            {(slotsData?.slots ?? []).length === 0 && (
              <p className="text-sm text-muted">No open slots this day.</p>
            )}
            {slotsData?.slots.map((slot) => {
              const active = selectedSlot?.start_at === slot.start_at;
              const label = new Date(slot.start_at + "Z").toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              });
              return (
                <button
                  key={slot.start_at}
                  onClick={() => setSelectedSlot(slot)}
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                    active
                      ? "border-primary bg-primary text-white"
                      : "border-line/70 text-ink hover:border-primary hover:text-primary"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm font-semibold">Reason</label>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Follow-up, annual checkup, …"
            className="input"
          />
        </div>

        <button
          onClick={book}
          disabled={busy || !patientId || !selectedSlot}
          className="btn-primary w-full"
        >
          {busy ? "Booking…" : "Book appointment"}
        </button>
      </div>
    </Sheet>
  );
}
