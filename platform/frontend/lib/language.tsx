"use client";

/** Language state: "en" | "es", localStorage-backed — mirrors lib/theme.ts.
 * Unlike theme (a CSS class toggle), translated text needs every mounted
 * component to re-render on change, so this is a React context instead of
 * a bare hook. */

import { createContext, useContext, useEffect, useState } from "react";

export type Lang = "en" | "es";

const LANG_KEY = "cac_lang";

const DICTIONARIES: Record<Lang, Record<string, string>> = {
  en: {
    "nav.search": "Search",
    "nav.logout": "Log out",

    "dashboard.title": "Overview",
    "dashboard.subtitle": "Who needs attention today",
    "dashboard.loading": "Loading overview…",
    "dashboard.backendDown": "Backend unreachable — start it with",
    "dashboard.stat.critical": "Critical",
    "dashboard.stat.moderate": "Moderate",
    "dashboard.stat.stable": "Stable",
    "dashboard.stat.maxPriority": "Max priority score",
    "dashboard.criticalPatients": "Critical patients",
    "dashboard.viewAll": "View all →",
    "dashboard.todaysAgenda": "Today's agenda",
    "dashboard.viewSchedule": "View schedule →",
    "dashboard.noAppointments": "No appointments today.",
    "dashboard.next": "Next",
    "dashboard.tabLoading": "Loading…",

    "tab.evolution": "Evolution",
    "tab.alerts": "Alerts",
    "tab.medication": "Medication",
    "tab.labs": "Labs",
    "tab.imaging": "Imaging",
    "tab.ai": "AI",
    "tab.evidence": "Evidence",
    "tab.pending": "Pending",
    "tab.performance": "Performance",
    "tab.automation": "Automation",
    "automation.tickHealth": "Tick health",
    "automation.healthy": "Healthy",
    "automation.behind": "Behind",
    "automation.workflowsActive": "Active workflows",
    "automation.stepsOverdue": "Overdue steps",
    "automation.approvalsPending": "Pending approvals",
    "automation.workflowsFailed": "Failed workflows",
    "automation.stepsRetried": "Retried steps",
    "automation.humanInterventionRate": "Human intervention rate",
    "automation.notificationReadRate": "Notification read rate",
    "approvals.title": "Approvals",
    "approvals.subtitle": "Review AI-drafted patient messages before they're sent — nothing reaches a patient without your approval.",
    "approvals.loading": "Loading…",
    "approvals.empty": "Nothing here.",
    "approvals.selectOne": "Select an item to review.",
    "approvals.generateDraft": "Generate draft",
    "approvals.drafting": "Drafting…",
    "approvals.emptyDraft": "No draft yet.",
    "approvals.approve": "Approve",
    "approvals.reject": "Reject",
    "approvals.confirmReject": "Confirm reject",
    "approvals.cancel": "Cancel",
    "approvals.reasonPlaceholder": "Why is this being rejected?",
    "approvals.rejectedReason": "Rejected",
    "approvals.approved": "Approved and sent to the patient.",
    "approvals.rejected": "Rejected.",
    "alerts.title": "Alerts",
    "alerts.subtitle": "Clinical alerts raised by the risk engine — review, then resolve.",
    "alerts.loading": "Loading…",
    "alerts.empty": "Nothing here.",
    "alerts.review": "Mark reviewed",
    "alerts.resolve": "Resolve",
    "alerts.reviewed": "Marked reviewed.",
    "alerts.resolvedToast": "Resolved.",

    "evolution.deteriorating": "Deteriorating",
    "evolution.improving": "Improving",
    "evolution.noChange": "No change",
    "evolution.newRiskFactors": "New risk factors",

    "alerts.active": "Active",
    "alerts.new24h": "New (24h)",
    "alerts.critical": "Critical",
    "alerts.pendingReview": "Pending review",
    "alerts.resolved": "Resolved",
    "alerts.avgReviewTime": "Average time to review",
    "alerts.min": "min",
    "alerts.none": "No alerts recorded.",

    "medication.interactions": "Interactions",
    "medication.contraindications": "Contraindications",
    "medication.highRisk": "High risk",
    "medication.doseAnomalies": "Dose anomalies",
    "medication.polypharmacy": "Polypharmacy patients",

    "labs.abnormal": "Abnormal",
    "labs.critical": "Critical",
    "labs.deterioratingTrend": "Deteriorating trend",
    "labs.significantChanges": "Significant changes",
    "labs.pending": "Pending",

    "imaging.analyzed": "Analyzed",
    "imaging.criticalFindings": "Critical findings",
    "imaging.requiresReview": "Requires review",
    "imaging.noFindings": "No findings",
    "imaging.newVsPrior": "New vs. prior",
    "imaging.pending": "Pending",

    "ai.evaluations": "Evaluations",
    "ai.highRiskPredictions": "High-risk predictions",
    "ai.avgConfidence": "Average confidence",
    "ai.requiresHumanReview": "Requires human review",
    "ai.modifiedByClinician": "Modified by clinician",
    "ai.rejectedByClinician": "Rejected by clinician",

    "evidence.withEvidence": "With evidence",
    "evidence.withoutEvidence": "Without sufficient evidence",
    "evidence.distinctSources": "Distinct sources",
    "evidence.avgSupportRatio": "Average support ratio",

    "pending.unresolvedIssues": "Unresolved issues",
    "pending.followUp": "Patients pending follow-up",
    "pending.recommendations": "Pending recommendations",
    "pending.requiresDecision": "Requires decision",

    "performance.avgResponseTime": "Average response time",
    "performance.alertsResolved": "Alerts resolved",
    "performance.falsePositives": "False positives",
    "performance.falseNegatives": "False negatives",
    "performance.sensitivity": "Sensitivity",
    "performance.specificity": "Specificity",

    "copilot.askOrTry": "Ask a clinical question, or try one of these:",
    "copilot.placeholder": "Ask a clinical question…",
    "copilot.agentsWorking": "Agents working…",
    "copilot.noPatient": "No patient",
    "copilot.failed": "Consultation failed — is the backend running?",
    "copilot.exportPreview": "Export preview",
    "copilot.includedSections": "Included sections",
    "copilot.cancel": "Cancel",
    "copilot.downloadPdf": "Download PDF",
    "copilot.citationGuard": "Citation Guard",
    "copilot.viewSource": "view source ↗",
    "copilot.fabricatedCitation": "could not be traced to any tool result; removed",
    "copilot.toolsUsed": "Tools used — click a call to inspect it",
  },
  es: {
    "nav.search": "Buscar",
    "nav.logout": "Cerrar sesión",

    "dashboard.title": "Resumen",
    "dashboard.subtitle": "Quién necesita atención hoy",
    "dashboard.loading": "Cargando resumen…",
    "dashboard.backendDown": "Backend inalcanzable — inícialo con",
    "dashboard.stat.critical": "Críticos",
    "dashboard.stat.moderate": "Moderados",
    "dashboard.stat.stable": "Estables",
    "dashboard.stat.maxPriority": "Puntaje de prioridad máxima",
    "dashboard.criticalPatients": "Pacientes críticos",
    "dashboard.viewAll": "Ver todos →",
    "dashboard.todaysAgenda": "Agenda de hoy",
    "dashboard.viewSchedule": "Ver agenda →",
    "dashboard.noAppointments": "Sin citas hoy.",
    "dashboard.next": "Próxima",
    "dashboard.tabLoading": "Cargando…",

    "tab.evolution": "Evolución",
    "tab.alerts": "Alertas",
    "tab.medication": "Medicación",
    "tab.labs": "Labs",
    "tab.imaging": "Imaging",
    "tab.ai": "IA",
    "tab.evidence": "Evidencia",
    "tab.pending": "Pendientes",
    "tab.performance": "Rendimiento",
    "tab.automation": "Automatización",
    "automation.tickHealth": "Estado del tick",
    "automation.healthy": "Saludable",
    "automation.behind": "Atrasado",
    "automation.workflowsActive": "Workflows activos",
    "automation.stepsOverdue": "Pasos atrasados",
    "automation.approvalsPending": "Aprobaciones pendientes",
    "automation.workflowsFailed": "Workflows fallidos",
    "automation.stepsRetried": "Pasos reintentados",
    "automation.humanInterventionRate": "Tasa de intervención humana",
    "automation.notificationReadRate": "Tasa de lectura de notificaciones",
    "approvals.title": "Aprobaciones",
    "approvals.subtitle": "Revisa los mensajes redactados por IA antes de enviarlos — nada llega al paciente sin tu aprobación.",
    "approvals.loading": "Cargando…",
    "approvals.empty": "No hay nada aquí.",
    "approvals.selectOne": "Selecciona un elemento para revisar.",
    "approvals.generateDraft": "Generar borrador",
    "approvals.drafting": "Redactando…",
    "approvals.emptyDraft": "Aún no hay borrador.",
    "approvals.approve": "Aprobar",
    "approvals.reject": "Rechazar",
    "approvals.confirmReject": "Confirmar rechazo",
    "approvals.cancel": "Cancelar",
    "approvals.reasonPlaceholder": "¿Por qué se rechaza?",
    "approvals.rejectedReason": "Rechazado",
    "approvals.approved": "Aprobado y enviado al paciente.",
    "approvals.rejected": "Rechazado.",
    "alerts.title": "Alertas",
    "alerts.subtitle": "Alertas clínicas generadas por el motor de riesgo — revisa y luego resuelve.",
    "alerts.loading": "Cargando…",
    "alerts.empty": "No hay nada aquí.",
    "alerts.review": "Marcar revisada",
    "alerts.resolve": "Resolver",
    "alerts.reviewed": "Marcada como revisada.",
    "alerts.resolvedToast": "Resuelta.",

    "evolution.deteriorating": "Deteriorando",
    "evolution.improving": "Mejorando",
    "evolution.noChange": "Sin cambios",
    "evolution.newRiskFactors": "Nuevos factores de riesgo",

    "alerts.active": "Activas",
    "alerts.new24h": "Nuevas (24h)",
    "alerts.critical": "Críticas",
    "alerts.pendingReview": "Pend. revisión",
    "alerts.resolved": "Resueltas",
    "alerts.avgReviewTime": "Tiempo promedio a revisión",
    "alerts.min": "min",
    "alerts.none": "Sin alertas registradas.",

    "medication.interactions": "Interacciones",
    "medication.contraindications": "Contraindicaciones",
    "medication.highRisk": "Alto riesgo",
    "medication.doseAnomalies": "Anomalías de dosis",
    "medication.polypharmacy": "Polimedicados",

    "labs.abnormal": "Anormales",
    "labs.critical": "Críticos",
    "labs.deterioratingTrend": "Tendencia deteriorante",
    "labs.significantChanges": "Cambios significativos",
    "labs.pending": "Pendientes",

    "imaging.analyzed": "Analizados",
    "imaging.criticalFindings": "Hallazgos críticos",
    "imaging.requiresReview": "Requieren revisión",
    "imaging.noFindings": "Sin hallazgos",
    "imaging.newVsPrior": "Nuevos vs. previo",
    "imaging.pending": "Pendientes",

    "ai.evaluations": "Evaluaciones",
    "ai.highRiskPredictions": "Predicciones alto riesgo",
    "ai.avgConfidence": "Confianza promedio",
    "ai.requiresHumanReview": "Requieren revisión humana",
    "ai.modifiedByClinician": "Modificadas por médico",
    "ai.rejectedByClinician": "Rechazadas por médico",

    "evidence.withEvidence": "Con evidencia",
    "evidence.withoutEvidence": "Sin evidencia suficiente",
    "evidence.distinctSources": "Fuentes distintas",
    "evidence.avgSupportRatio": "Ratio de respaldo promedio",

    "pending.unresolvedIssues": "Problemas sin resolver",
    "pending.followUp": "Pacientes pend. seguimiento",
    "pending.recommendations": "Recomendaciones pendientes",
    "pending.requiresDecision": "Requieren decisión",

    "performance.avgResponseTime": "Tiempo resp. promedio",
    "performance.alertsResolved": "Alertas resueltas",
    "performance.falsePositives": "Falsos positivos",
    "performance.falseNegatives": "Falsos negativos",
    "performance.sensitivity": "Sensibilidad",
    "performance.specificity": "Especificidad",

    "copilot.askOrTry": "Haz una pregunta clínica, o prueba una de estas:",
    "copilot.placeholder": "Haz una pregunta clínica…",
    "copilot.agentsWorking": "Agentes trabajando…",
    "copilot.noPatient": "Sin paciente",
    "copilot.failed": "La consulta falló — ¿está corriendo el backend?",
    "copilot.exportPreview": "Vista previa de exportación",
    "copilot.includedSections": "Secciones incluidas",
    "copilot.cancel": "Cancelar",
    "copilot.downloadPdf": "Descargar PDF",
    "copilot.citationGuard": "Citation Guard",
    "copilot.viewSource": "ver fuente ↗",
    "copilot.fabricatedCitation": "no se pudo rastrear a ningún resultado de herramienta; eliminada",
    "copilot.toolsUsed": "Herramientas usadas — haz clic en una para inspeccionarla",
  },
};

export function getLanguage(): Lang {
  if (typeof window === "undefined") return "en";
  return (localStorage.getItem(LANG_KEY) as Lang | null) ?? "en";
}

/** Maps our short codes to the words the LLM system prompt needs. */
export function languageName(lang: Lang): string {
  return lang === "es" ? "Spanish" : "English";
}

interface LanguageContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    setLangState(getLanguage());
  }, []);

  const setLang = (next: Lang) => {
    localStorage.setItem(LANG_KEY, next);
    setLangState(next);
  };

  const t = (key: string): string => DICTIONARIES[lang][key] ?? DICTIONARIES.en[key] ?? key;

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error("useLanguage must be used within a LanguageProvider");
  return ctx;
}
