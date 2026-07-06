"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, FlaskConical, Pill, ScanEye, BookOpenCheck } from "lucide-react";
import { api } from "@/lib/api";
import StatusPill from "@/components/status-pill";
import AgentBadge from "@/components/agent-badge";

const agentMeta: Record<string, { icon: typeof Bot; description: string; tools: string }> = {
  Evidence: {
    icon: BookOpenCheck,
    description: "Retrieves clinical guidelines and PubMed literature. Every claim is cited.",
    tools: "search_clinical_guidelines · search_pubmed",
  },
  Radiology: {
    icon: ScanEye,
    description: "Inspects and analyzes medical images across five modalities.",
    tools: "inspect_medical_image · analyze_medical_image",
  },
  Laboratory: {
    icon: FlaskConical,
    description: "Interprets lab values against reference ranges and trends.",
    tools: "patient context only",
  },
  "Drug Safety": {
    icon: Pill,
    description: "Screens medication lists for drug-drug interactions.",
    tools: "check_drug_interactions",
  },
  Coordinator: {
    icon: Bot,
    description: "Synthesizes all specialist outputs into one cited response.",
    tools: "extract_medical_entities · summarize_clinical_note",
  },
};

export default function AgentsPage() {
  const { data } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboardStats });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-extrabold">Agents Activity</h1>
          <p className="text-sm text-muted">
            Specialist agents running locally on {data?.system.model ?? "Ollama"}
          </p>
        </div>
        <AgentBadge name="100% local" />
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
                <span className="font-semibold">MCP tools:</span> {meta.tools}
              </div>
              <div className="mt-3 text-sm">
                <span className="text-2xl font-extrabold">{agent.consultations}</span>{" "}
                <span className="text-muted">consultations</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
