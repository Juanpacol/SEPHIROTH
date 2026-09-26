"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { api, type ClinicalAlert } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { useToast } from "@/components/ui/toast";
import StatusPill from "@/components/status-pill";
import { parseInteractionLabel, riskLabel } from "@/lib/clinical-text";

const STATUS_FILTERS = ["active", "reviewed", "resolved"] as const;

function alertCategory(category: string, t: (key: string) => string): string {
  const key = `alerts.category.${category}`;
  const translated = t(key);
  return translated === key ? category : translated;
}

function alertTitle(title: string, t: (key: string) => string): string {
  const interaction = parseInteractionLabel(title);
  if (interaction) {
    return t("clinical.interaction").replace("{drugA}", interaction.drugA).replace("{drugB}", interaction.drugB);
  }
  return riskLabel(title, t);
}

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
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <div className="min-w-0">
          <p className="font-semibold">{alertTitle(alert.title, t)}</p>
          <p className="text-xs text-muted">
            {t("alerts.patient").replace("{id}", alert.patient_id)} · {alertCategory(alert.category, t)}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusPill label={alert.severity} />
          <StatusPill label={alert.status} />
        </div>
      </div>
      {alert.detail && <p className="text-sm text-ink/80">{alert.detail}</p>}
      <div className="flex flex-wrap gap-2">
        {alert.status === "active" && (
          <button
            onClick={() => review.mutate()}
            disabled={review.isPending}
            className="btn-primary tap w-full sm:w-auto"
          >
            {t("alerts.review")}
          </button>
        )}
        {alert.status === "reviewed" && (
          <button
            onClick={() => resolve.mutate()}
            disabled={resolve.isPending}
            className="btn-primary tap w-full sm:w-auto"
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

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setStatus(f)}
            className={`tap shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${
              status === f ? "bg-primary text-white" : "bg-primary-soft text-primary"
            }`}
          >
            {t(`alerts.filter.${f}`)}
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
