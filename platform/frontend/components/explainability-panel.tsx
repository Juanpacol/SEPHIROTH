"use client";

import { useState } from "react";
import {
  BookOpenCheck,
  Brain,
  ChevronDown,
  ChevronRight,
  Eye,
  FileSearch,
  FlaskConical,
  Pill,
  ScanEye,
  type LucideIcon,
} from "lucide-react";
import type { Explanation } from "@/lib/api";

const toolIcons: Record<string, LucideIcon> = {
  search_clinical_guidelines: BookOpenCheck,
  search_pubmed: FileSearch,
  check_drug_interactions: Pill,
  inspect_medical_image: ScanEye,
  analyze_medical_image: ScanEye,
  describe_medical_image: Eye,
  extract_medical_entities: FileSearch,
  summarize_clinical_note: FileSearch,
};

/** Collapsible "why did the AI say that" trace under each answer. */
export default function ExplainabilityPanel({ explanation }: { explanation: Explanation }) {
  const [open, setOpen] = useState(false);
  if (!explanation.steps?.length) return null;

  return (
    <div className="rounded-xl bg-surface p-3 text-xs">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-1 font-semibold text-ink/80"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Brain size={13} className="text-primary" />
        How this answer was produced
        <span className="ml-auto font-normal text-muted">
          {explanation.citations_verified} citation(s) verified
          {explanation.citations_removed > 0 &&
            ` · ${explanation.citations_removed} removed by Citation Guard`}
        </span>
      </button>
      {open && (
        <ol className="mt-2 space-y-1.5 border-l-2 border-line/60 pl-3">
          {explanation.steps.map((step, i) => {
            const Icon = toolIcons[step.tool] ?? FlaskConical;
            return (
              <li key={i} className="flex items-start gap-1.5 text-muted">
                <Icon size={12} className="mt-0.5 shrink-0 text-primary" />
                <span>
                  <span className="font-semibold text-ink/70">{step.agent}</span>{" "}
                  {step.action}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
