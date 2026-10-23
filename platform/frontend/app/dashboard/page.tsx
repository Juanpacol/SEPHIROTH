"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, ClipboardList } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import ActionItemsList from "@/components/action-items-list";
import AccentTitle from "@/components/landing/accent-title";
import Reveal from "@/components/landing/reveal";
import {
  AgendaPanel,
  AlertRing,
  EvolutionBar,
  KpiStrip,
  MedicationBars,
  QualityRing,
  RiskDonut,
  VitalsWatch,
} from "@/components/dashboard/insight-charts";
import RuleSummaryChart from "@/components/dashboard/rule-summary-chart";

export default function DashboardPage() {
  const { t } = useLanguage();

  const {
    data: bootstrap,
    isLoading,
    error,
  } = useQuery({
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
  const { data: evolution } = useQuery({
    queryKey: ["dashboard", "evolution"],
    queryFn: api.dashboardEvolution,
    refetchInterval: 60_000,
  });
  const { data: alerts } = useQuery({
    queryKey: ["dashboard", "alerts"],
    queryFn: api.dashboardAlerts,
    refetchInterval: 60_000,
  });
  const { data: vitals } = useQuery({
    queryKey: ["dashboard", "vitals"],
    queryFn: api.dashboardVitals,
    refetchInterval: 60_000,
  });
  const { data: medications } = useQuery({
    queryKey: ["dashboard", "medications"],
    queryFn: api.dashboardMedications,
    refetchInterval: 60_000,
  });
  const data = bootstrap?.stats;

  if (isLoading) return <div className="text-muted">{t("dashboard.loading")}</div>;
  if (error || !data)
    return (
      <div className="card text-danger">
        {t("dashboard.backendDown")}{" "}
        <code className="rounded bg-surface px-1">PYTHONPATH=.:platform uvicorn api.main:app</code>
      </div>
    );

  return (
    <div className="space-y-2.5">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-1">
        <div className="min-w-0">
          <div className="eyebrow text-primary-ink">Sephiroth</div>
          <AccentTitle
            as="h1"
            text={t("dashboard.title")}
            accentWords={1}
            accentClass="text-primary-ink"
            className="mt-0.5 text-3xl sm:text-4xl"
          />
        </div>
        <p className="max-w-md pb-1 text-sm text-muted">{t("dashboard.subtitle")}</p>
      </header>

      <Reveal>
        <KpiStrip
          critical={data.critical_count}
          worsening={evolution?.deteriorating_count ?? 0}
          unreviewed={alerts?.pending_review_count ?? 0}
          vitals={vitals?.abnormal_patient_count ?? 0}
        />
      </Reveal>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        <div className="space-y-2.5 lg:col-span-8">
          <Reveal className="dash-panel flex flex-col !p-5 hover:!ring-line/60">
            <h2 className="eyebrow mb-1 flex items-center gap-2 text-muted">
              <ClipboardList size={13} className="text-primary-ink" /> {t("dashboard.actionItems.title")}
            </h2>
            <div className="max-h-[19rem] overflow-y-auto">
              <ActionItemsList groups={bootstrap?.action_items.groups ?? []} maxVisible={5} />
            </div>
          </Reveal>
          {vitals && (
            <Reveal delay={80}>
              <VitalsWatch data={vitals} />
            </Reveal>
          )}
        </div>

        <div className="space-y-2.5 lg:col-span-4">
          {bootstrap?.agenda && (
            <Reveal delay={60}>
              <AgendaPanel agenda={bootstrap.agenda} />
            </Reveal>
          )}
          <Reveal delay={120}>
            <RiskDonut
              critical={data.critical_count}
              moderate={data.moderate_count}
              stable={data.stable_count}
            />
          </Reveal>
          {alerts && (
            <Reveal delay={180}>
              <AlertRing data={alerts} />
            </Reveal>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-2">
        {evolution && (
          <Reveal>
            <EvolutionBar data={evolution} />
          </Reveal>
        )}
        {medications && (
          <Reveal delay={80}>
            <MedicationBars data={medications} />
          </Reveal>
        )}
        {quality && (
          <Reveal>
            <QualityRing data={quality} />
          </Reveal>
        )}
        <Reveal delay={80} className="dash-panel !p-5">
          <div className="mb-1 flex items-start justify-between gap-2">
            <h2 className="eyebrow flex items-center gap-2 text-muted">
              <BarChart3 size={13} className="text-primary-ink" /> {t("dashboard.ruleSummary.title")}
            </h2>
            <Link href="/patients?sort=risk" className="link-underline shrink-0 text-xs font-semibold">
              {t("dashboard.viewAll")}
            </Link>
          </div>
          {ruleSummary && <RuleSummaryChart summary={ruleSummary} />}
        </Reveal>
      </div>
    </div>
  );
}
