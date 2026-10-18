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
import type { Explanation, LLMCall } from "@/lib/api";
import { useLanguage } from "@/lib/language";

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

const PROVIDER_NAMES: Record<string, string> = { gemini: "Gemini", groq: "Groq", ollama: "Ollama" };

/** Reason codes the API can send; anything else is shown as-is. */
const KNOWN_REASONS = new Set([
  "rate_limited",
  "no_api_key",
  "auth_error",
  "timeout",
  "unreachable",
  "server_error",
  "model_not_found",
  "no_vision_support",
  "phi_not_allowed",
  "cancelled",
  "internal_error",
  "unavailable",
]);

/** Collapsible "why did the AI say that" trace under each answer.
 *
 * `llmCalls` says which provider and model really served each model call
 * (from the consultation's trace); `undefined` means the trace is not known
 * here, an empty list means no model was called. It is kept apart from
 * `explanation` on purpose: that one is a pure function of the persisted
 * agents, tool calls and citations (charter §2.4) and must not start
 * depending on the trace. */
export default function ExplainabilityPanel({
  explanation,
  llmCalls,
  traceId,
}: {
  explanation: Explanation;
  llmCalls?: LLMCall[];
  traceId?: string;
}) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  if (!explanation.steps?.length && !llmCalls?.length) return null;

  const reasonText = (code: string) => (KNOWN_REASONS.has(code) ? t(`explainability.reason.${code}`) : code);

  return (
    <div className="rounded-xl bg-surface p-3 text-xs text-muted">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-1 font-semibold"
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        <Brain size={13} />
        {t("explainability.title")}
      </button>
      {open && (
        <ol className="mt-2 space-y-1.5 border-l-2 border-line/60 pl-3">
          {explanation.steps.map((step, i) => {
            const Icon = toolIcons[step.tool] ?? FlaskConical;
            return (
              <li key={i} className="flex items-start gap-1.5">
                <Icon size={12} className="mt-0.5 shrink-0" />
                <span>
                  <span className="font-semibold">{step.agent}</span> {step.action}
                </span>
              </li>
            );
          })}
        </ol>
      )}
      {open && llmCalls !== undefined && (
        <div className="mt-3 border-t border-line/60 pt-2">
          <div className="font-semibold">{t("explainability.models")}</div>
          {llmCalls.length === 0 ? (
            <p className="mt-1">{t("explainability.noModel")}</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {llmCalls.map((call, i) => (
                <li key={i} className="flex flex-wrap items-baseline gap-x-1.5">
                  <span className="font-semibold">{t(`explainability.kind.${call.kind}`)}</span>
                  <span>
                    {PROVIDER_NAMES[call.provider] ?? call.provider} · {call.model}
                  </span>
                  {call.fallback && (
                    <span className="rounded bg-primary-soft px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                      {t("explainability.fallback")}
                    </span>
                  )}
                  {!call.ok && (
                    <span className="rounded bg-danger/10 px-1.5 py-0.5 text-[10px] font-semibold text-danger">
                      {t("explainability.failed").replace("{reason}", reasonText(call.error))}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {open && traceId && (
        <p className="mt-2 break-all">
          {t("explainability.traceId")}: <span className="select-all font-mono">{traceId}</span>
        </p>
      )}
    </div>
  );
}
