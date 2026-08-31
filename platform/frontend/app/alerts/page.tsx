"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { api, type ClinicalAlert } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { useToast } from "@/components/ui/toast";
import StatusPill from "@/components/status-pill";

const STATUS_FILTERS = ["active", "reviewed", "resolved"] as const;

function AlertRow({ alert }: { alert: ClinicalAlert }) {
  const { t } = useLanguage();
  const showToast = useToast();
  const queryClient = useQueryClient();

  const review = useMutation({
    mutationFn: () => api.reviewAlert(alert.id),
    onSuccess: () => {
      showToast(t("alerts.reviewed"));
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: () => showToast(t("alerts.error.review"), "error"),
  });

  const resolve = useMutation({
    mutationFn: () => api.resolveAlert(alert.id),
    onSuccess: () => {
      showToast(t("alerts.resolvedToast"));
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: () => showToast(t("alerts.error.resolve"), "error"),
  });

  return (
    <div className="card space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{alert.title}</p>
          <p className="text-xs text-muted">
            Patient {alert.patient_id} · {alert.category}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill label={alert.severity} />
          <StatusPill label={alert.status} />
        </div>
      </div>
      {alert.detail && <p className="text-sm text-ink/80">{alert.detail}</p>}
      <div className="flex gap-2">
        {alert.status === "active" && (
          <button
            onClick={() => review.mutate()}
            disabled={review.isPending}
            className="btn-primary"
          >
            {t("alerts.review")}
          </button>
        )}
        {alert.status === "reviewed" && (
          <button
            onClick={() => resolve.mutate()}
            disabled={resolve.isPending}
            className="btn-primary"
          >
            {t("alerts.resolve")}
          </button>
        )}
      </div>
    </div>
  );
}

export default function AlertsPage() {
  const { t } = useLanguage();
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>("active");

  const { data: alerts, isLoading } = useQuery({
    queryKey: ["alerts", status],
    queryFn: () => api.listAlerts({ status }),
  });

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-extrabold">
          <Bell size={20} className="text-primary" /> {t("alerts.title")}
        </h1>
        <p className="text-sm text-muted">{t("alerts.subtitle")}</p>
      </div>

      <div className="flex gap-2">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setStatus(f)}
            className={`rounded-full px-3 py-1 text-xs font-semibold capitalize ${
              status === f ? "bg-primary text-white" : "bg-primary-soft text-primary"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {isLoading && <p className="text-sm text-muted">{t("alerts.loading")}</p>}
        {alerts?.length === 0 && <p className="card text-sm text-muted">{t("alerts.empty")}</p>}
        {alerts?.map((a) => <AlertRow key={a.id} alert={a} />)}
      </div>
    </div>
  );
}
