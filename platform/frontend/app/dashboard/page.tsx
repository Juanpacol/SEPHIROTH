"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, ClipboardList, ThumbsUp } from "lucide-react";
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
  const { data: quality } = useQuery({
    queryKey: ["dashboard", "ai"],
    queryFn: api.dashboardAI,
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

      {quality && (
        <div className="card !p-4" data-testid="answer-quality">
          <h2 className="flex items-center gap-2 text-sm font-bold">
            <ThumbsUp size={15} className="text-primary" /> {t("dashboard.quality.title")}
          </h2>
          <p className="text-xs text-muted">{t("dashboard.quality.subtitle")}</p>
          {quality.auto_graded_count > 0 && (
            <div className="mt-3 border-t border-line/60 pt-3" data-testid="auto-grades">
              <p className="text-xs text-muted">
                {t("dashboard.quality.autoGraded").replace("{count}", String(quality.auto_graded_count))}
              </p>
              <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
                {(["grounding", "completeness", "safety", "abstention"] as const).map((c) => (
                  <div key={c} className="min-w-0">
                    <dt className="truncate text-xs text-muted">{t(`dashboard.quality.criterion.${c}`)}</dt>
                    <dd className="font-bold">{quality.auto_grade_averages[c]?.toFixed(1) ?? "—"} / 5</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
          {quality.helpful_ratio === null ? (
            <p className="mt-2 text-sm text-muted">{t("dashboard.quality.none")}</p>
          ) : (
            <div className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-3xl font-extrabold text-primary">{Math.round(quality.helpful_ratio * 100)}%</span>
              <span className="text-sm text-muted">{t("dashboard.quality.helpful")}</span>
              <span className="text-xs text-muted">
                {t("dashboard.quality.ratings").replace("{count}", String(quality.ratings_count))}
              </span>
              <span className={`text-xs font-semibold ${quality.pending_review_count > 0 ? "text-warning" : "text-muted"}`}>
                {t("dashboard.quality.pending").replace("{count}", String(quality.pending_review_count))}
              </span>
            </div>
          )}
        </div>
      )}

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

