"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api, type ClinicalAlert } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { useToast } from "@/components/ui/toast";
import StatusPill from "@/components/status-pill";
import FilterTabs from "@/components/ui/filter-tabs";
import PageHeader from "@/components/ui/page-header";
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
    return t("clinical.interaction")
      .replace("{drugA}", interaction.drugA)
      .replace("{drugB}", interaction.drugB);
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

  const edge = alert.severity === "critical" || alert.severity === "high" ? "bg-danger" : "bg-warning";

  return (
    <li className="relative flex flex-col gap-2 py-4 pl-4 pr-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <span aria-hidden className={`absolute inset-y-4 left-0 w-0.5 rounded-full ${edge}`} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold">{alertTitle(alert.title, t)}</p>
          <StatusPill label={alert.severity} />
        </div>
        <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
          <Link href={`/patients/${alert.patient_id}`} className="nav-underline hover:text-ink">
            {t("alerts.patient").replace("{id}", alert.patient_id)}
          </Link>
          {" · "}
          {alertCategory(alert.category, t)}
        </p>
        {alert.detail && <p className="mt-1.5 text-sm text-muted">{alert.detail}</p>}
      </div>
      <div className="flex shrink-0 gap-2">
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
            className="btn-secondary tap w-full sm:w-auto"
          >
            {t("alerts.resolve")}
          </button>
        )}
      </div>
    </li>
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
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader eyebrow={t("patients.eyebrow")} title={t("alerts.title")} subtitle={t("alerts.subtitle")} />

      <FilterTabs
        label={t("alerts.title")}
        value={status}
        onChange={setStatus}
        tabs={STATUS_FILTERS.map((f) => ({ value: f, label: t(`alerts.filter.${f}`) }))}
      />

      {isLoading && <p className="text-sm text-muted">{t("alerts.loading")}</p>}
      {alerts?.length === 0 && <p className="card text-sm text-muted">{t("alerts.empty")}</p>}
      {alerts && alerts.length > 0 && (
        <ul className="card divide-y divide-line/50 !py-1">
          {alerts.map((a) => (
            <AlertRow key={a.id} alert={a} />
          ))}
        </ul>
      )}
    </div>
  );
}
