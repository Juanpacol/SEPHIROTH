"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, FlaskConical, Pill, ScanEye, BookOpenCheck } from "lucide-react";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";
import AgentBadge from "@/components/agent-badge";

export default function AgentsPage() {
  const { t } = useLanguage();
  const { data } = useQuery({ queryKey: ["agents-status"], queryFn: api.agentsStatus });

  const agentMeta: Record<string, { icon: typeof Bot; description: string; tools: string }> = {
    Evidence: {
      icon: BookOpenCheck,
      description: t("agents.evidence.description"),
      tools: "search_clinical_guidelines · search_pubmed",
    },
    Radiology: {
      icon: ScanEye,
      description: t("agents.radiology.description"),
      tools: "inspect_medical_image · analyze_medical_image",
    },
    Laboratory: {
      icon: FlaskConical,
      description: t("agents.laboratory.description"),
      tools: t("agents.laboratory.tools"),
    },
    "Drug Safety": {
      icon: Pill,
      description: t("agents.drugSafety.description"),
      tools: "check_drug_interactions",
    },
    Coordinator: {
      icon: Bot,
      description: t("agents.coordinator.description"),
      tools: "extract_medical_entities · summarize_clinical_note",
    },
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-extrabold">{t("nav.agents")}</h1>
          <p className="text-sm text-muted">
            {t("agents.subtitle").replace("{model}", data?.system.model ?? "Gemini")}
          </p>
        </div>
        <AgentBadge name={t("agents.cloudAi")} />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data?.agents.map((agent) => {
          const meta = agentMeta[agent.name] ?? agentMeta.Coordinator;
          const Icon = meta.icon;
          return (
            <div key={agent.name} className="card">
              <div className="flex items-center justify-between">
                <span className="ai-ring flex h-10 w-10 items-center justify-center rounded-xl bg-card">
                  <Icon size={18} className="text-primary" />
                </span>
                <StatusPill label={agent.status} />
              </div>
              <h2 className="mt-3 font-bold">{agent.name}</h2>
              <p className="mt-1 text-sm text-muted">{meta.description}</p>
              <div className="mt-3 rounded-xl bg-surface px-3 py-2 text-xs text-muted">
                <span className="font-semibold">{t("agents.mcpTools")}</span> {meta.tools}
              </div>
              <div className="mt-3 text-sm">
                <span className="text-2xl font-extrabold">{agent.consultations}</span>{" "}
                <span className="text-muted">{t("agents.consultations")}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
