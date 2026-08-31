"use client";

/** The Copilot Chat conversation itself — extracted verbatim from the old
 * dedicated `/copilot` page so it can be dropped into the floating
 * `CopilotWidget` (mounted app-wide in AppShell) instead of requiring a
 * navigation away from whatever the clinician was looking at. No page-level
 * chrome (h1/subtitle) here; the widget's own header carries that. */

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  Download,
  Loader2,
  Send,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { api, type CitationReport, type Explanation, type ToolCall } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import AgentBadge from "@/components/agent-badge";
import AnswerText from "@/components/copilot/answer-text";
import ExplainabilityPanel from "@/components/explainability-panel";

interface AgentProgress {
  name: string;
  done: boolean;
  toolCalls: { name: string }[];
}

interface Exchange {
  id?: string;
  question: string;
  answer?: string;
  agents?: string[];
  toolCalls?: ToolCall[];
  citations?: CitationReport;
  explanation?: Explanation;
  progress?: AgentProgress[];
  pending?: boolean;
  error?: string;
}

/** Suggested starter questions — kept in English regardless of UI locale,
 * matching the clinical literature/citations the agents cite.
 *
 * Ordered general reference first, then specialist decisions. Every one was
 * checked against the retrieval corpus (`data/rag`) before being listed: a
 * suggested question the corpus cannot answer abstains, which reads as the
 * product being broken rather than as it being careful. The last one routes
 * to the drug-safety agent rather than evidence, so the set exercises both
 * answering paths. */
const SUGGESTED_QUESTIONS = [
  "What blood pressure reading is considered high?",
  "What are the warning signs of a stroke?",
  "What is the A1C target for adults with type 2 diabetes?",
  "When should anticoagulation be started in atrial fibrillation?",
  "Which empiric antibiotics for outpatient community-acquired pneumonia?",
  "Which patients with type 2 diabetes and CKD should get an SGLT2 inhibitor?",
  "Do warfarin and ibuprofen interact?",
];

/** Token-overlap match — mirrors the >=0.5 overlap threshold Citation Guard
 * uses server-side (`citation_guard._is_verified`) so a link only attaches
 * when the citation text plausibly came from that tool result. */
function tokensOf(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .match(/[a-z0-9/]+/g)
      ?.filter((t) => t.length > 1) ?? []
  );
}

function citationUrl(citation: string, toolCalls: ToolCall[] | undefined): string | null {
  if (!toolCalls) return null;
  const candidateTokens = tokensOf(citation);
  if (candidateTokens.size === 0) return null;

  let best: { url: string; overlap: number } | null = null;
  for (const call of toolCalls) {
    const results = (call.result as { results?: unknown[] } | undefined)?.results;
    if (!Array.isArray(results)) continue;
    for (const item of results) {
      if (typeof item !== "object" || item === null) continue;
      const { citation: label, source, title, url } = item as Record<string, unknown>;
      const text = [label, source, title].find((v) => typeof v === "string") as string | undefined;
      if (!text || typeof url !== "string") continue;
      const overlap =
        Array.from(tokensOf(text)).filter((t) => candidateTokens.has(t)).length / candidateTokens.size;
      if (overlap >= 0.5 && (!best || overlap > best.overlap)) best = { url, overlap };
    }
  }
  return best?.url ?? null;
}

interface PdfPreview {
  exchangeId: string;
  url: string;
  size: number;
  sections: string[];
}

function reportSections(exchange: Exchange): string[] {
  const citationCount =
    (exchange.citations?.verified?.length ?? 0) + (exchange.citations?.fabricated?.length ?? 0);
  return [
    "Clinical question & AI response",
    exchange.agents?.length ? "Agents involved" : null,
    citationCount > 0 ? "Citation Guard" : null,
    exchange.explanation?.steps.length ? "Reasoning trace" : null,
    "Disclaimer",
  ].filter((s): s is string => Boolean(s));
}

function PdfPreviewModal({
  preview,
  onClose,
  onConfirm,
}: {
  preview: PdfPreview;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const { t } = useLanguage();
  return (
    <div
      className="fixed inset-0 z-[60] flex animate-fadeIn items-center justify-center bg-ink/40 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-card shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line/60 p-4">
          <div>
            <h2 className="font-bold">{t("copilot.exportPreview")}</h2>
            <p className="text-xs text-muted">
              {(preview.size / 1024).toFixed(0)} KB · SEPHIROTH Consultation Report
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close preview"
            className="rounded-full p-1.5 text-muted hover:bg-surface"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-hidden bg-surface">
          <iframe src={preview.url} title="PDF preview" className="h-[50vh] w-full" />
        </div>

        <div className="border-t border-line/60 p-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
            {t("copilot.includedSections")}
          </p>
          <ul className="mb-4 space-y-1">
            {preview.sections.map((section) => (
              <li key={section} className="flex items-center gap-1.5 text-sm">
                <CheckCircle2 size={13} className="text-success" /> {section}
              </li>
            ))}
          </ul>
          <div className="flex justify-end gap-2">
            <button
              onClick={onClose}
              className="rounded-xl border border-line/70 px-4 py-2 text-sm font-semibold text-ink/80 hover:bg-surface"
            >
              {t("copilot.cancel")}
            </button>
            <button
              onClick={onConfirm}
              className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white"
            >
              <Download size={14} /> {t("copilot.downloadPdf")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-0.5" aria-hidden>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1 w-1 animate-thinkingDot rounded-full bg-current"
          style={{ animationDelay: `${i * 0.18}s` }}
        />
      ))}
    </span>
  );
}

function CitationsPanel({ report, toolCalls }: { report: CitationReport; toolCalls?: ToolCall[] }) {
  const { t } = useLanguage();
  const verified = report.verified ?? [];
  const fabricated = report.fabricated ?? [];
  if (verified.length === 0 && fabricated.length === 0) return null;
  return (
    <div className="rounded-xl bg-surface p-3 text-xs text-muted">
      <div className="mb-1.5 flex items-center gap-1 font-semibold">
        <ShieldCheck size={13} /> {t("copilot.citationGuard")}
      </div>
      {verified.map((citation) => {
        const url = citationUrl(citation, toolCalls);
        return (
          <div key={citation} className="flex items-start gap-1.5">
            <CheckCircle2 size={12} className="mt-0.5 shrink-0" />
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="underline underline-offset-2"
              >
                {citation} — {t("copilot.viewSource")}
              </a>
            ) : (
              <span>{citation}</span>
            )}
          </div>
        );
      })}
      {fabricated.map((citation) => (
        <div key={citation} className="flex items-start gap-1.5 text-danger">
          <ShieldAlert size={12} className="mt-0.5 shrink-0" />
          <span>
            &ldquo;{citation}&rdquo; — {t("copilot.fabricatedCitation")}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function CopilotPanel({ initialQuery = "" }: { initialQuery?: string }) {
  const { lang, t } = useLanguage();
  const [query, setQuery] = useState(initialQuery);
  const [patientId, setPatientId] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [pdfPreview, setPdfPreview] = useState<PdfPreview | null>(null);
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null);
  const [inputFocused, setInputFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize, same idea as kokonutui's useAutoResizeTextarea: grow with
  // content up to a cap, then let the textarea itself scroll.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [query]);

  const openPdfPreview = async (exchange: Exchange) => {
    if (!exchange.id) return;
    setPreviewLoadingId(exchange.id);
    try {
      const blob = await api.exportConsultation(exchange.id);
      setPdfPreview({
        exchangeId: exchange.id,
        url: URL.createObjectURL(blob),
        size: blob.size,
        sections: reportSections(exchange),
      });
    } finally {
      setPreviewLoadingId(null);
    }
  };

  const closePdfPreview = () => {
    if (pdfPreview) URL.revokeObjectURL(pdfPreview.url);
    setPdfPreview(null);
  };

  const confirmPdfDownload = () => {
    if (!pdfPreview) return;
    const a = document.createElement("a");
    a.href = pdfPreview.url;
    a.download = `consultation-${pdfPreview.exchangeId.slice(0, 8)}.pdf`;
    a.click();
    closePdfPreview();
  };

  const { data: patients } = useQuery({ queryKey: ["patients"], queryFn: () => api.patients() });

  const patch = (update: Partial<Exchange>) =>
    setExchanges((prev) =>
      prev.map((e, i) => (i === prev.length - 1 ? { ...e, ...update } : e))
    );

  const submit = async (override?: string) => {
    const text = override ?? query;
    if (!text.trim() || streaming) return;
    const patient = patients?.find((p) => p.id === patientId);
    const q = text;
    setQuery("");
    setStreaming(true);
    setExchanges((prev) => [...prev, { question: q, pending: true, progress: [] }]);

    try {
      const res = await fetch("/api/agents/consult/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          query: q,
          patient_id: patientId,
          context: { ...(patient ? { conditions: patient.conditions } : {}), language: lang },
        }),
      });
      if (!res.ok || !res.body) throw new Error(`${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          if (!chunk.startsWith("data: ")) continue;
          const event = JSON.parse(chunk.slice(6));

          if (event.event === "routing") {
            patch({
              progress: (event.agents as string[]).map((name) => ({
                name: name.replace("_", "-"),
                done: false,
                toolCalls: [],
              })),
            });
          } else if (event.event === "agent_completed") {
            setExchanges((prev) =>
              prev.map((e, i) =>
                i === prev.length - 1
                  ? {
                      ...e,
                      progress: e.progress?.map((p) =>
                        p.name === event.agent || p.name.replace("-", "_") === event.agent
                          ? { ...p, done: true, toolCalls: event.tool_calls }
                          : p
                      ),
                    }
                  : e
              )
            );
          } else if (event.event === "final") {
            patch({
              pending: false,
              answer: event.answer,
              agents: event.agents_involved,
              toolCalls: event.tool_calls,
              citations: event.citation_report,
              explanation: event.explanation,
            });
          } else if (event.event === "persisted") {
            patch({ id: event.id });
          } else if (event.event === "error") {
            patch({ pending: false, error: event.detail });
          }
        }
      }
    } catch {
      patch({ pending: false, error: t("copilot.failed") });
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex-1 space-y-4 overflow-y-auto">
        {exchanges.length === 0 && (
          <div className="card space-y-2.5 text-sm text-muted">
            <p>{t("copilot.askOrTry")}</p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => submit(q)}
                  disabled={streaming}
                  className="rounded-full border border-line/70 bg-card px-3 py-1.5 text-xs font-medium text-ink/80 transition-colors hover:border-primary hover:text-primary disabled:opacity-40"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {exchanges.map((exchange, i) => (
          <div key={i} className="space-y-3">
            <div className="ml-auto w-fit max-w-[85%] rounded-2xl bg-primary px-4 py-2.5 text-sm text-white">
              {exchange.question}
            </div>
            {/* No `ai-ring` here: its 2px #8c92ac halo read as a stray light
                border around every answer. The AI-provenance signal that ring
                carried (design decision #4) still ships on each answer via
                AgentBadge, which uses the same Sephiroth gradient. */}
            <div className="max-w-[95%] rounded-squircle bg-card p-4 text-sm shadow-card">
              {exchange.pending ? (
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                    {t("copilot.agentsWorking")}
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {exchange.progress?.map((agent) => (
                      <span
                        key={agent.name}
                        role="status"
                        className={`inline-flex animate-fadeIn items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold transition-all ${
                          agent.done ? "ai-badge" : "bg-surface text-muted"
                        }`}
                      >
                        {agent.done ? <CheckCircle2 size={11} /> : <ThinkingDots />}
                        {agent.name}
                        {agent.toolCalls.length > 0 &&
                          ` · ${agent.toolCalls.map((t) => t.name).join(", ")}`}
                      </span>
                    ))}
                  </div>
                </div>
              ) : exchange.error ? (
                <span className="text-danger">{exchange.error}</span>
              ) : (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {exchange.agents?.map((agent) => (
                      <AgentBadge key={agent} name={agent} />
                    ))}
                    {exchange.id && (
                      <button
                        onClick={() => openPdfPreview(exchange)}
                        disabled={previewLoadingId === exchange.id}
                        aria-label="Preview and export this consultation as PDF"
                        title="Export as PDF"
                        className="ml-auto rounded-full p-1.5 text-muted hover:bg-surface hover:text-primary disabled:opacity-40"
                      >
                        {previewLoadingId === exchange.id ? (
                          <span className="block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                        ) : (
                          <Download size={14} />
                        )}
                      </button>
                    )}
                  </div>
                  <AnswerText answer={exchange.answer ?? ""} />
                  {exchange.citations && (
                    <CitationsPanel report={exchange.citations} toolCalls={exchange.toolCalls} />
                  )}
                  {exchange.explanation && (
                    <ExplainabilityPanel explanation={exchange.explanation} />
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div
        className={`flex cursor-text flex-col rounded-squircle bg-card shadow-card ring-1 ring-line/70 transition-all duration-200 ${
          inputFocused ? "ring-primary/50" : ""
        }`}
        onClick={() => textareaRef.current?.focus()}
      >
        <textarea
          ref={textareaRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          onFocus={() => setInputFocused(true)}
          onBlur={() => setInputFocused(false)}
          placeholder={t("copilot.placeholder")}
          rows={1}
          className="max-h-40 min-h-[44px] w-full resize-none bg-transparent px-4 pt-3 text-sm leading-relaxed outline-none placeholder:text-muted"
        />
        <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5 pt-1.5">
          <select
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            className="rounded-full border-none bg-surface px-3 py-1.5 text-xs font-medium text-ink/70 outline-none"
          >
            <option value="">{t("copilot.noPatient")}</option>
            {patients?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            onClick={() => submit()}
            disabled={streaming || !query.trim()}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
              query.trim() && !streaming
                ? "bg-primary-soft text-primary"
                : "bg-surface text-muted"
            } disabled:cursor-not-allowed`}
            aria-label="Send"
          >
            {streaming ? (
              <Loader2 size={15} className="animate-spin" />
            ) : (
              <Send size={15} />
            )}
          </button>
        </div>
      </div>

      {pdfPreview && (
        <PdfPreviewModal
          preview={pdfPreview}
          onClose={closePdfPreview}
          onConfirm={confirmPdfDownload}
        />
      )}
    </div>
  );
}
