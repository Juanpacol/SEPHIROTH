"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import StatusPill from "@/components/status-pill";

export default function PortalAppointmentsPage() {
  const queryClient = useQueryClient();
  const showToast = useToast();
  const { data: appointments, isLoading } = useQuery({
    queryKey: ["portal", "appointments"],
    queryFn: () => api.listAppointments(),
  });

  const cancel = async (id: string) => {
    try {
      await api.cancelAppointment(id, "Cancelled by patient");
      await queryClient.invalidateQueries({ queryKey: ["portal", "appointments"] });
      showToast("Appointment cancelled.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not cancel this appointment.", "error");
    }
  };

  const confirm = async (id: string) => {
    try {
      await api.confirmAppointment(id);
      await queryClient.invalidateQueries({ queryKey: ["portal", "appointments"] });
      showToast("Appointment confirmed.");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Could not confirm this appointment.", "error");
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">Appointments</h1>

      {isLoading && <p className="text-sm text-muted">Loading…</p>}
      {!isLoading && (appointments ?? []).length === 0 && (
        <p className="text-sm text-muted">You have no appointments yet.</p>
      )}

      <div className="space-y-3">
        {(appointments ?? [])
          .slice()
          .sort((a, b) => a.start_at.localeCompare(b.start_at))
          .map((a) => (
            <div key={a.id} className="card flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold">
                  {new Date(a.start_at + "Z").toLocaleString([], {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
                <div className="text-xs text-muted">
                  {a.mode === "telehealth" ? "Telehealth" : "In person"}
                  {a.reason ? ` · ${a.reason}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <StatusPill label={a.status.replace("_", " ")} />
                {a.status === "booked" && !a.confirmed_at && (
                  <button
                    onClick={() => confirm(a.id)}
                    className="text-xs font-semibold text-primary hover:underline"
                  >
                    Confirm
                  </button>
                )}
                {a.status === "booked" && (
                  <button
                    onClick={() => cancel(a.id)}
                    className="text-xs font-semibold text-danger hover:underline"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
