"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ShieldAlert } from "lucide-react";
import { api, type DashboardAlerts } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import CriticalPatientsList from "@/components/critical-patients-list";
import StatCard from "@/components/stat-card";
import StatusPill from "@/components/status-pill";

const TABS = [
  "evolution",
  "alerts",
  "medication",
  "labs",
  "imaging",
  "ai",
  "evidence",
  "pending",
  "performance",
  "automation",
] as const;
type Tab = (typeof TABS)[number];

export default function DashboardPage() {
  const [tab, setTab] = useState<Tab>("alerts");
  const { t } = useLanguage();

  const { data: bootstrap, isLoading, error } = useQuery({
    queryKey: ["dashboard", "bootstrap"],
    queryFn: api.dashboardBootstrap,
    refetchInterval: 30_000,
  });
  const data = bootstrap?.stats;
  const agenda = bootstrap?.agenda;

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
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-extrabold">{t("dashboard.title")}</h1>
        <p className="text-sm text-muted">{t("dashboard.subtitle")}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label={t("dashboard.stat.critical")} value={data.critical_count} tone="danger" />
        <StatCard label={t("dashboard.stat.moderate")} value={data.moderate_count} tone="warning" />
        <StatCard label={t("dashboard.stat.stable")} value={data.stable_count} tone="success" />
        <StatCard label={t("dashboard.stat.maxPriority")} value={data.max_priority_score} tone="primary" />
      </div>

      <div className="card">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-bold">
            <ShieldAlert size={16} className="text-primary" /> {t("dashboard.criticalPatients")}
          </h2>
          <Link href="/patients?sort=risk" className="text-sm font-semibold text-primary">
            {t("dashboard.viewAll")}
          </Link>
        </div>
        <CriticalPatientsList patients={data.critical_patients} />
      </div>

      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-bold">
            <CalendarClock size={16} className="text-primary" /> {t("dashboard.todaysAgenda")}
          </h2>
          <Link href="/schedule" className="text-sm font-semibold text-primary">
            {t("dashboard.viewSchedule")}
          </Link>
        </div>
        {!agenda || agenda.count === 0 ? (
          <p className="text-sm text-muted">{t("dashboard.noAppointments")}</p>
        ) : (
          <>
            <p className="mb-2 text-sm text-muted">
              {agenda.count} appointment{agenda.count > 1 ? "s" : ""}
              {agenda.next_at &&
                ` · ${t("dashboard.next")}: ${new Date(agenda.next_at + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
            </p>
            <ul className="space-y-1.5 text-sm">
              {agenda.items.slice(0, 4).map((item) => (
                <li key={item.id} className="flex justify-between">
                  <span className="font-medium">{item.patient_name}</span>
                  <span className="text-muted">
                    {new Date(item.start_at + "Z").toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="card">
        <div className="mb-3 flex flex-wrap gap-1 border-b border-line/60 pb-2">
          {TABS.map((tabKey) => (
            <button
              key={tabKey}
              onClick={() => setTab(tabKey)}
              className={`rounded-full px-3 py-1 text-sm font-semibold ${
                tab === tabKey ? "bg-primary text-white" : "text-muted hover:bg-primary-soft/40"
              }`}
            >
              {t(`tab.${tabKey}`)}
            </button>
          ))}
        </div>
        {tab === "evolution" && <EvolutionTab />}
        {tab === "alerts" && <AlertsTab initialData={bootstrap?.alerts} />}
        {tab === "medication" && <MedicationsTab />}
        {tab === "labs" && <LabsTab />}
        {tab === "imaging" && <ImagingTab />}
        {tab === "ai" && <AITab />}
        {tab === "evidence" && <EvidenceTab />}
        {tab === "pending" && <PendingTab />}
        {tab === "performance" && <PerformanceTab />}
        {tab === "automation" && <AutomationTab />}
      </div>
    </div>
  );
}

const TAB_STALE_TIME = 20_000;

function EvolutionTab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "evolution"],
    queryFn: api.dashboardEvolution,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label={t("evolution.deteriorating")} value={data.deteriorating_count} tone="danger" />
        <StatCard label={t("evolution.improving")} value={data.improving_count} tone="success" />
        <StatCard label={t("evolution.noChange")} value={data.no_change_count} />
        <StatCard label={t("evolution.newRiskFactors")} value={data.new_risk_factors_count} tone="warning" />
      </div>
    </div>
  );
}

function AlertsTab({ initialData }: { initialData?: DashboardAlerts }) {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "alerts"],
    queryFn: api.dashboardAlerts,
    initialData,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <StatCard label={t("alerts.active")} value={data.active_count} tone="warning" />
        <StatCard label={t("alerts.new24h")} value={data.new_count} />
        <StatCard label={t("alerts.critical")} value={data.critical_count} tone="danger" />
        <StatCard label={t("alerts.pendingReview")} value={data.pending_review_count} />
        <StatCard label={t("alerts.resolved")} value={data.resolved_count} tone="success" />
      </div>
      {data.avg_review_seconds !== null && (
        <p className="text-sm text-muted">
          {t("alerts.avgReviewTime")}: {Math.round(data.avg_review_seconds / 60)} {t("alerts.min")}
        </p>
      )}
      <ul className="divide-y divide-line/60">
        {data.recent.map((a) => (
          <li key={a.id} className="flex items-center justify-between py-2 text-sm">
            <span className="font-medium">{a.title}</span>
            <span className="flex items-center gap-2">
              <StatusPill label={a.severity} />
              <StatusPill label={a.status} />
            </span>
          </li>
        ))}
        {data.recent.length === 0 && <li className="py-2 text-sm text-muted">{t("alerts.none")}</li>}
      </ul>
    </div>
  );
}

function MedicationsTab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "medications"],
    queryFn: api.dashboardMedications,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
      <StatCard label={t("medication.interactions")} value={data.interaction_count} tone="warning" />
      <StatCard label={t("medication.contraindications")} value={data.contraindication_count} tone="danger" />
      <StatCard label={t("medication.highRisk")} value={data.high_risk_medication_count} tone="danger" />
      <StatCard label={t("medication.doseAnomalies")} value={data.dose_anomaly_count} />
      <StatCard label={t("medication.polypharmacy")} value={data.polypharmacy_patient_count} />
    </div>
  );
}

function LabsTab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "labs"],
    queryFn: api.dashboardLabs,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
      <StatCard label={t("labs.abnormal")} value={data.abnormal_count} tone="warning" />
      <StatCard label={t("labs.critical")} value={data.critical_count} tone="danger" />
      <StatCard label={t("labs.deterioratingTrend")} value={data.deteriorating_trend_count} tone="danger" />
      <StatCard label={t("labs.significantChanges")} value={data.significant_change_count} />
      <StatCard label={t("labs.pending")} value={data.pending_count} />
    </div>
  );
}

function ImagingTab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "imaging"],
    queryFn: api.dashboardImaging,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
      <StatCard label={t("imaging.analyzed")} value={data.analyzed_count} />
      <StatCard label={t("imaging.criticalFindings")} value={data.critical_finding_count} tone="danger" />
      <StatCard label={t("imaging.requiresReview")} value={data.requires_review_count} tone="warning" />
      <StatCard label={t("imaging.noFindings")} value={data.no_relevant_finding_count} tone="success" />
      <StatCard label={t("imaging.newVsPrior")} value={data.new_finding_vs_prior_count} tone="warning" />
      <StatCard label={t("imaging.pending")} value={data.pending_count} />
    </div>
  );
}

function AITab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "ai"],
    queryFn: api.dashboardAI,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label={t("ai.evaluations")} value={data.evaluations_count} />
      <StatCard label={t("ai.highRiskPredictions")} value={data.high_risk_prediction_count} tone="danger" />
      <StatCard
        label={t("ai.avgConfidence")}
        value={data.avg_confidence !== null ? `${Math.round(data.avg_confidence * 100)}%` : null}
        tone="primary"
      />
      <StatCard label={t("ai.requiresHumanReview")} value={data.requires_human_review_count} tone="warning" />
      <StatCard label={t("ai.modifiedByClinician")} value={data.clinician_modified_count} />
      <StatCard label={t("ai.rejectedByClinician")} value={data.clinician_rejected_count} />
    </div>
  );
}

function EvidenceTab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "evidence"],
    queryFn: api.dashboardEvidence,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label={t("evidence.withEvidence")} value={data.recommendations_with_evidence_count} tone="success" />
      <StatCard label={t("evidence.withoutEvidence")} value={data.recommendations_without_evidence_count} tone="warning" />
      <StatCard label={t("evidence.distinctSources")} value={data.distinct_sources_used} />
      <StatCard
        label={t("evidence.avgSupportRatio")}
        value={data.avg_supported_claim_ratio !== null ? `${Math.round(data.avg_supported_claim_ratio * 100)}%` : null}
      />
    </div>
  );
}

function PendingTab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "pending"],
    queryFn: api.dashboardPending,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label={t("pending.unresolvedIssues")} value={data.unresolved_clinical_issues_count} tone="warning" />
      <StatCard label={t("pending.followUp")} value={data.patients_pending_follow_up_count} />
      <StatCard label={t("pending.recommendations")} value={data.pending_recommendations_count} />
      <StatCard label={t("pending.requiresDecision")} value={data.cases_requiring_decision_count} tone="danger" />
    </div>
  );
}

function PerformanceTab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "performance"],
    queryFn: api.dashboardPerformance,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label={t("performance.avgResponseTime")}
          value={data.avg_alert_response_seconds !== null ? `${Math.round(data.avg_alert_response_seconds / 60)} min` : null}
        />
        <StatCard label={t("performance.alertsResolved")} value={data.alerts_resolved_count} tone="success" />
        <StatCard label={t("performance.falsePositives")} value={data.false_positive_count} tone="warning" />
        <StatCard label={t("performance.falseNegatives")} value={data.false_negative_count} tone="danger" />
        <StatCard
          label={t("performance.sensitivity")}
          value={data.sensitivity !== null ? `${Math.round(data.sensitivity * 100)}%` : null}
        />
        <StatCard
          label={t("performance.specificity")}
          value={data.specificity !== null ? `${Math.round(data.specificity * 100)}%` : null}
        />
        <StatCard label="AUC" value={data.auc ?? "N/D"} />
      </div>
      <p className="text-xs text-muted">{data.methodology}</p>
    </div>
  );
}

function AutomationTab() {
  const { t } = useLanguage();
  const { data } = useQuery({
    queryKey: ["dashboard", "automation"],
    queryFn: api.dashboardAutomation,
    staleTime: TAB_STALE_TIME,
  });
  if (!data) return <TabLoading />;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label={t("automation.tickHealth")}
          value={data.tick_health.status === "healthy" ? t("automation.healthy") : t("automation.behind")}
          tone={data.tick_health.status === "healthy" ? "success" : "danger"}
        />
        <StatCard label={t("automation.workflowsActive")} value={data.workflows.active} tone="primary" />
        <StatCard label={t("automation.stepsOverdue")} value={data.steps.overdue} tone="warning" />
        <StatCard label={t("automation.approvalsPending")} value={data.approvals.pending} tone="warning" />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label={t("automation.workflowsFailed")} value={data.workflows.failed} tone="danger" />
        <StatCard label={t("automation.stepsRetried")} value={data.steps.retried} />
        <StatCard
          label={t("automation.humanInterventionRate")}
          value={`${Math.round(data.approvals.human_intervention_rate * 100)}%`}
        />
        <StatCard
          label={t("automation.notificationReadRate")}
          value={data.notifications.read_rate !== null ? `${Math.round(data.notifications.read_rate * 100)}%` : "N/D"}
        />
      </div>
      <p className="text-xs text-muted">{data.methodology}</p>
    </div>
  );
}

function TabLoading() {
  const { t } = useLanguage();
  return <div className="text-sm text-muted">{t("dashboard.tabLoading")}</div>;
}
