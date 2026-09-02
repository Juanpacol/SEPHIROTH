"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/toast";
import StatusPill from "@/components/status-pill";
import { useLanguage } from "@/lib/language";

export default function PortalAppointmentsPage() {
  const queryClient = useQueryClient();
  const showToast = useToast();
  const { t } = useLanguage();
  const { data: appointments, isLoading } = useQuery({
    queryKey: ["portal", "appointments"],
    queryFn: () => api.listAppointments(),
  });

  const cancel = async (id: string) => {
    try {
      await api.cancelAppointment(id, "Cancelled by patient");
      await queryClient.invalidateQueries({ queryKey: ["portal", "appointments"] });
      showToast(t("portal.appointments.cancelled"));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("portal.appointments.error.cancel"), "error");
    }
  };

  const confirm = async (id: string) => {
    try {
      await api.confirmAppointment(id);
      await queryClient.invalidateQueries({ queryKey: ["portal", "appointments"] });
      showToast(t("portal.appointments.confirmed"));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("portal.appointments.error.confirm"), "error");
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">{t("portal.appointments.title")}</h1>

      {isLoading && <p className="text-sm text-muted">{t("portal.appointments.loading")}</p>}
      {!isLoading && (appointments ?? []).length === 0 && (
        <p className="text-sm text-muted">{t("portal.appointments.empty")}</p>
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
                  {a.mode === "telehealth" ? t("portal.appointments.telehealth") : t("portal.appointments.inPerson")}
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
                    {t("portal.appointments.confirm")}
                  </button>
                )}
                {a.status === "booked" && (
                  <button
                    onClick={() => cancel(a.id)}
                    className="text-xs font-semibold text-danger hover:underline"
                  >
                    {t("portal.appointments.cancel")}
                  </button>
                )}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
