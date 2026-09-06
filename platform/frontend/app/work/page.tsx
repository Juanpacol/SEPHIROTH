"use client";

/** The work center — what a clinician opens first (SPEC-019).
 *
 * It replaces `/dashboard`, and the rename is the point: the old page led with
 * how many patients fall into each risk bucket, which is a fact about the
 * panel rather than a thing to do. This one is ordered by what someone acts
 * on: what is happening today, what is waiting, who is deteriorating.
 *
 * Three counters instead of four. `moderate_count`, `stable_count` and
 * `max_priority_score` are not decisions — nobody opens the app and does
 * something because the stable count moved — so they are gone from here;
 * `/patients` computes its own bucket counts for filtering, which is where
 * that number belongs.
 *
 * The order below is also the mobile order: one column always, splitting 2/1
 * from `lg`.
 */

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CheckSquare, ShieldAlert } from "lucide-react";

import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { useBadgeCounts } from "@/lib/hooks/use-badge-counts";
import ActionItemsList from "@/components/action-items-list";
import CriticalPatientsList from "@/components/critical-patients-list";
import StatCard from "@/components/stat-card";
import AgendaTodayCard from "@/components/work/agenda-today-card";
import { SkeletonRows } from "@/components/ui/skeleton";

export default function WorkCenterPage() {
  const { t } = useLanguage();
  const { data: counts } = useBadgeCounts();

  const {
    data: bootstrap,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["dashboard", "bootstrap"],
    queryFn: api.dashboardBootstrap,
    refetchInterval: 30_000,
  });

  if (isLoading) return <SkeletonRows rows={4} label={t("work.loading")} />;

  if (error || !bootstrap) {
    return (
      <div className="card text-danger">
        {t("dashboard.backendDown")}{" "}
        <code className="rounded bg-surface px-1">PYTHONPATH=.:platform uvicorn api.main:app</code>
      </div>
    );
  }

  const stats = bootstrap.stats;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-extrabold">{t("work.title")}</h1>
        <p className="text-sm text-muted">{t("work.subtitle")}</p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <StatCard label={t("work.stat.tasks")} value={counts?.tasks_open ?? 0} tone="primary" />
        <StatCard label={t("work.stat.criticalAlerts")} value={counts?.alerts_active ?? 0} tone="danger" />
        <StatCard label={t("work.stat.appointments")} value={bootstrap.agenda?.count ?? 0} tone="default" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <AgendaTodayCard agenda={bootstrap.agenda} />

          <div className="card !p-4">
            <div className="mb-1 flex items-center justify-between gap-2">
              <h2 className="flex items-center gap-2 text-sm font-bold">
                <CheckSquare size={15} className="text-primary" /> {t("work.tasks.title")}
              </h2>
              <Link href="/tasks" className="text-xs font-semibold text-primary">
                {t("work.viewAll")}
              </Link>
            </div>
            {/* Still the bootstrap payload rather than the task API: with
                `enable_task_inbox` off these are derived rows with no id, and
                `ActionItemsList` already handles both — it offers actions when
                a row has a `task_id` and reads as text when it does not. */}
            <ActionItemsList items={bootstrap.action_items.items} maxVisible={5} />
          </div>
        </div>

        <div className="card !p-4">
          <div className="mb-1 flex items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-sm font-bold">
              <ShieldAlert size={15} className="text-primary" /> {t("work.criticalPatients")}
            </h2>
            <Link href="/patients?sort=risk" className="text-xs font-semibold text-primary">
              {t("work.viewAll")}
            </Link>
          </div>
          <CriticalPatientsList patients={stats.critical_patients} maxVisible={5} />
        </div>
      </div>
    </div>
  );
}
