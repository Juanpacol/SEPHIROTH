"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import ActionItemsList from "@/components/action-items-list";
import CriticalPatientsList from "@/components/critical-patients-list";
import StatCard from "@/components/stat-card";

export default function DashboardPage() {
  const { t } = useLanguage();

  const { data: bootstrap, isLoading, error } = useQuery({
    queryKey: ["dashboard", "bootstrap"],
    queryFn: api.dashboardBootstrap,
    refetchInterval: 30_000,
  });
  const data = bootstrap?.stats;

  if (isLoading) return <div className="text-muted">{t("dashboard.loading")}</div>;
  if (error || !data)
    return (
      <div className="card text-danger">
        {t("dashboard.backendDown")}{" "}
        <code className="rounded bg-surface px-1">
          PYTHONPATH=.:platform uvicorn api.main:app
        </code>
      </div>
    );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-extrabold">{t("dashboard.title")}</h1>
        <p className="text-sm text-muted">{t("dashboard.subtitle")}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label={t("dashboard.stat.critical")} value={data.critical_count} tone="danger" />
        <StatCard label={t("dashboard.stat.moderate")} value={data.moderate_count} tone="warning" />
        <StatCard label={t("dashboard.stat.stable")} value={data.stable_count} tone="success" />
        <StatCard label={t("dashboard.stat.maxPriority")} value={data.max_priority_score} tone="primary" />
      </div>

      <div className="card !p-4">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold">
            <ShieldAlert size={15} className="text-primary" /> {t("dashboard.criticalPatients")}
          </h2>
          <Link href="/patients?sort=risk" className="text-xs font-semibold text-primary">
            {t("dashboard.viewAll")}
          </Link>
        </div>
        <CriticalPatientsList patients={data.critical_patients} maxVisible={5} />
      </div>

      <div className="card !p-4">
        <h2 className="mb-1 flex items-center gap-2 text-sm font-bold">
          <ClipboardList size={15} className="text-primary" /> {t("dashboard.actionItems.title")}
        </h2>
        <ActionItemsList items={bootstrap?.action_items.items ?? []} maxVisible={6} />
      </div>
    </div>
  );
}

