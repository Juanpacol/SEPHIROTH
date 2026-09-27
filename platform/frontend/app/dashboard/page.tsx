"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, ClipboardList } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import ActionItemsList from "@/components/action-items-list";
import StatCard from "@/components/stat-card";
import RiskDistribution from "@/components/dashboard/risk-distribution";
import RuleSummaryChart from "@/components/dashboard/rule-summary-chart";

export default function DashboardPage() {
  const { t } = useLanguage();

  const { data: bootstrap, isLoading, error } = useQuery({
    queryKey: ["dashboard", "bootstrap"],
    queryFn: api.dashboardBootstrap,
    refetchInterval: 30_000,
  });
  const { data: ruleSummary } = useQuery({
    queryKey: ["dashboard", "rule-summary"],
    queryFn: api.dashboardRuleSummary,
    refetchInterval: 60_000,
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

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <RiskDistribution
          critical={data.critical_count}
          moderate={data.moderate_count}
          stable={data.stable_count}
        />
        <StatCard
          label={t("dashboard.stat.maxPriority")}
          value={data.max_priority_score}
          tone="primary"
          suffix={t("dashboard.stat.maxPriorityOf")}
          hint={t("dashboard.stat.maxPriorityHint")}
        />
      </div>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="card !p-4">
          <h2 className="mb-1 flex items-center gap-2 text-sm font-bold">
            <ClipboardList size={15} className="text-primary" /> {t("dashboard.actionItems.title")}
          </h2>
          <ActionItemsList groups={bootstrap?.action_items.groups ?? []} maxVisible={6} />
        </div>

        <div className="card !p-4">
          <div className="mb-2 flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h2 className="flex items-center gap-2 text-sm font-bold">
                <BarChart3 size={15} className="text-primary" /> {t("dashboard.ruleSummary.title")}
              </h2>
              <p className="text-xs text-muted">{t("dashboard.ruleSummary.subtitle")}</p>
            </div>
            <Link href="/patients?sort=risk" className="shrink-0 text-xs font-semibold text-primary">
              {t("dashboard.viewAll")}
            </Link>
          </div>
          {ruleSummary && <RuleSummaryChart summary={ruleSummary} />}
        </div>
      </div>
    </div>
  );
}

