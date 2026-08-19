"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CalendarClock, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import CriticalPatientsList from "@/components/critical-patients-list";
import StatCard from "@/components/stat-card";
import StatusPill from "@/components/status-pill";

const TABS = [
  "Evolución",
  "Alertas",
  "Medicación",
  "Labs",
  "Imaging",
  "IA",
  "Evidencia",
  "Pendientes",
  "Rendimiento",
] as const;
type Tab = (typeof TABS)[number];

export default function DashboardPage() {
  const [tab, setTab] = useState<Tab>("Alertas");

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboardStats,
    refetchInterval: 30_000,
  });
  const { data: agenda } = useQuery({
    queryKey: ["agenda", "today"],
    queryFn: api.agendaToday,
    refetchInterval: 60_000,
  });

  if (isLoading) return <div className="text-muted">Loading overview…</div>;
  if (error || !data)
    return (
      <div className="card text-danger">
        Backend unreachable — start it with{" "}
        <code className="rounded bg-surface px-1">
          PYTHONPATH=.:platform uvicorn api.main:app
        </code>
      </div>
    );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-extrabold">Overview</h1>
        <p className="text-sm text-muted">Who needs attention today</p>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Critical" value={data.critical_count} tone="danger" />
        <StatCard label="Moderate" value={data.moderate_count} tone="warning" />
        <StatCard label="Stable" value={data.stable_count} tone="success" />
        <StatCard label="Max priority score" value={data.max_priority_score} tone="primary" />
      </div>

      <div className="card">
        <div className="mb-1 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-bold">
            <ShieldAlert size={16} className="text-primary" /> Critical patients
          </h2>
          <Link href="/patients?sort=risk" className="text-sm font-semibold text-primary">
            View all →
          </Link>
        </div>
        <CriticalPatientsList patients={data.critical_patients} />
      </div>

      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-bold">
            <CalendarClock size={16} className="text-primary" /> Today&apos;s agenda
          </h2>
          <Link href="/schedule" className="text-sm font-semibold text-primary">
            View schedule →
          </Link>
        </div>
        {!agenda || agenda.count === 0 ? (
          <p className="text-sm text-muted">No appointments today.</p>
        ) : (
          <>
            <p className="mb-2 text-sm text-muted">
              {agenda.count} appointment{agenda.count > 1 ? "s" : ""}
              {agenda.next_at &&
                ` · Next: ${new Date(agenda.next_at + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}
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
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-full px-3 py-1 text-sm font-semibold ${
                tab === t ? "bg-primary text-white" : "text-muted hover:bg-primary-soft/40"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        {tab === "Evolución" && <EvolutionTab />}
        {tab === "Alertas" && <AlertsTab />}
        {tab === "Medicación" && <MedicationsTab />}
        {tab === "Labs" && <LabsTab />}
        {tab === "Imaging" && <ImagingTab />}
        {tab === "IA" && <AITab />}
        {tab === "Evidencia" && <EvidenceTab />}
        {tab === "Pendientes" && <PendingTab />}
        {tab === "Rendimiento" && <PerformanceTab />}
      </div>
    </div>
  );
}

function EvolutionTab() {
  const { data } = useQuery({ queryKey: ["dashboard", "evolution"], queryFn: api.dashboardEvolution });
  if (!data) return <TabLoading />;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Deteriorando" value={data.deteriorating_count} tone="danger" />
        <StatCard label="Mejorando" value={data.improving_count} tone="success" />
        <StatCard label="Sin cambios" value={data.no_change_count} />
        <StatCard label="Nuevos factores de riesgo" value={data.new_risk_factors_count} tone="warning" />
      </div>
    </div>
  );
}

function AlertsTab() {
  const { data } = useQuery({ queryKey: ["dashboard", "alerts"], queryFn: api.dashboardAlerts });
  if (!data) return <TabLoading />;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <StatCard label="Activas" value={data.active_count} tone="warning" />
        <StatCard label="Nuevas (24h)" value={data.new_count} />
        <StatCard label="Críticas" value={data.critical_count} tone="danger" />
        <StatCard label="Pend. revisión" value={data.pending_review_count} />
        <StatCard label="Resueltas" value={data.resolved_count} tone="success" />
      </div>
      {data.avg_review_seconds !== null && (
        <p className="text-sm text-muted">
          Tiempo promedio a revisión: {Math.round(data.avg_review_seconds / 60)} min
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
        {data.recent.length === 0 && <li className="py-2 text-sm text-muted">Sin alertas registradas.</li>}
      </ul>
    </div>
  );
}

function MedicationsTab() {
  const { data } = useQuery({ queryKey: ["dashboard", "medications"], queryFn: api.dashboardMedications });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
      <StatCard label="Interacciones" value={data.interaction_count} tone="warning" />
      <StatCard label="Contraindicaciones" value={data.contraindication_count} tone="danger" />
      <StatCard label="Alto riesgo" value={data.high_risk_medication_count} tone="danger" />
      <StatCard label="Anomalías de dosis" value={data.dose_anomaly_count} />
      <StatCard label="Polimedicados" value={data.polypharmacy_patient_count} />
    </div>
  );
}

function LabsTab() {
  const { data } = useQuery({ queryKey: ["dashboard", "labs"], queryFn: api.dashboardLabs });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
      <StatCard label="Anormales" value={data.abnormal_count} tone="warning" />
      <StatCard label="Críticos" value={data.critical_count} tone="danger" />
      <StatCard label="Tendencia deteriorante" value={data.deteriorating_trend_count} tone="danger" />
      <StatCard label="Cambios significativos" value={data.significant_change_count} />
      <StatCard label="Pendientes" value={data.pending_count} />
    </div>
  );
}

function ImagingTab() {
  const { data } = useQuery({ queryKey: ["dashboard", "imaging"], queryFn: api.dashboardImaging });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
      <StatCard label="Analizados" value={data.analyzed_count} />
      <StatCard label="Hallazgos críticos" value={data.critical_finding_count} tone="danger" />
      <StatCard label="Requieren revisión" value={data.requires_review_count} tone="warning" />
      <StatCard label="Sin hallazgos" value={data.no_relevant_finding_count} tone="success" />
      <StatCard label="Nuevos vs. previo" value={data.new_finding_vs_prior_count} tone="warning" />
      <StatCard label="Pendientes" value={data.pending_count} />
    </div>
  );
}

function AITab() {
  const { data } = useQuery({ queryKey: ["dashboard", "ai"], queryFn: api.dashboardAI });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label="Evaluaciones" value={data.evaluations_count} />
      <StatCard label="Predicciones alto riesgo" value={data.high_risk_prediction_count} tone="danger" />
      <StatCard
        label="Confianza promedio"
        value={data.avg_confidence !== null ? `${Math.round(data.avg_confidence * 100)}%` : null}
        tone="primary"
      />
      <StatCard label="Requieren revisión humana" value={data.requires_human_review_count} tone="warning" />
      <StatCard label="Modificadas por médico" value={data.clinician_modified_count} />
      <StatCard label="Rechazadas por médico" value={data.clinician_rejected_count} />
    </div>
  );
}

function EvidenceTab() {
  const { data } = useQuery({ queryKey: ["dashboard", "evidence"], queryFn: api.dashboardEvidence });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label="Con evidencia" value={data.recommendations_with_evidence_count} tone="success" />
      <StatCard label="Sin evidencia suficiente" value={data.recommendations_without_evidence_count} tone="warning" />
      <StatCard label="Fuentes distintas" value={data.distinct_sources_used} />
      <StatCard
        label="Ratio de respaldo promedio"
        value={data.avg_supported_claim_ratio !== null ? `${Math.round(data.avg_supported_claim_ratio * 100)}%` : null}
      />
    </div>
  );
}

function PendingTab() {
  const { data } = useQuery({ queryKey: ["dashboard", "pending"], queryFn: api.dashboardPending });
  if (!data) return <TabLoading />;
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <StatCard label="Problemas sin resolver" value={data.unresolved_clinical_issues_count} tone="warning" />
      <StatCard label="Pacientes pend. seguimiento" value={data.patients_pending_follow_up_count} />
      <StatCard label="Recomendaciones pendientes" value={data.pending_recommendations_count} />
      <StatCard label="Requieren decisión" value={data.cases_requiring_decision_count} tone="danger" />
    </div>
  );
}

function PerformanceTab() {
  const { data } = useQuery({ queryKey: ["dashboard", "performance"], queryFn: api.dashboardPerformance });
  if (!data) return <TabLoading />;
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Tiempo resp. promedio"
          value={data.avg_alert_response_seconds !== null ? `${Math.round(data.avg_alert_response_seconds / 60)} min` : null}
        />
        <StatCard label="Alertas resueltas" value={data.alerts_resolved_count} tone="success" />
        <StatCard label="Falsos positivos" value={data.false_positive_count} tone="warning" />
        <StatCard label="Falsos negativos" value={data.false_negative_count} tone="danger" />
        <StatCard
          label="Sensibilidad"
          value={data.sensitivity !== null ? `${Math.round(data.sensitivity * 100)}%` : null}
        />
        <StatCard
          label="Especificidad"
          value={data.specificity !== null ? `${Math.round(data.specificity * 100)}%` : null}
        />
        <StatCard label="AUC" value={data.auc ?? "N/D"} />
      </div>
      <p className="text-xs text-muted">{data.methodology}</p>
    </div>
  );
}

function TabLoading() {
  return <div className="text-sm text-muted">Cargando…</div>;
}
