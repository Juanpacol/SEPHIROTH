"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  Download,
  Send,
  ShieldAlert,
  ShieldCheck,
  Wrench,
  X,
} from "lucide-react";
import { api, type CitationReport, type Explanation, type ToolCall } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import AgentBadge from "@/components/agent-badge";
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
  return (
    <div
      className="fixed inset-0 z-50 flex animate-fadeIn items-center justify-center bg-ink/40 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-card shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-line/60 p-4">
          <div>
            <h2 className="font-bold">Export preview</h2>
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
            Included sections
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
              Cancel
            </button>
            <button
              onClick={onConfirm}
              className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white"
            >
              <Download size={14} /> Download PDF
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

function ToolCallRow({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const hasDetail = call.arguments || call.result !== undefined;
  return (
    <div className="border-b border-line/50 last:border-0">
      <button
        onClick={() => hasDetail && setOpen((o) => !o)}
        className={`flex w-full items-center gap-1.5 py-1.5 text-left ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
        aria-expanded={open}
      >
        {hasDetail && (
          <ChevronDown
            size={11}
            className={`shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
          />
        )}
        <span className="truncate">
          {call.agent && <span className="text-muted">{call.agent} → </span>}
          <code className="text-ink/80">{call.name}</code>
        </span>
      </button>
      {open && hasDetail && (
        <pre className="mb-2 max-h-48 overflow-auto rounded-lg bg-card p-2 text-[11px] leading-relaxed text-muted">
{JSON.stringify({ arguments: call.arguments, result: call.result }, null, 2)}
        </pre>
      )}
    </div>
  );
}

function CitationsPanel({ report }: { report: CitationReport }) {
  const verified = report.verified ?? [];
  const fabricated = report.fabricated ?? [];
  if (verified.length === 0 && fabricated.length === 0) return null;
  return (
    <div className="rounded-xl bg-surface p-3 text-xs">
      <div className="mb-1.5 flex items-center gap-1 font-semibold text-ink/80">
        <ShieldCheck size={13} className="text-success" /> Citation Guard
      </div>
      {verified.map((citation) => (
        <div key={citation} className="flex items-start gap-1.5 text-muted">
          <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-success" />
          <span>{citation}</span>
        </div>
      ))}
      {fabricated.map((citation) => (
        <div key={citation} className="flex items-start gap-1.5 text-danger">
          <ShieldAlert size={12} className="mt-0.5 shrink-0" />
          <span>
            &ldquo;{citation}&rdquo; — could not be traced to any tool result; removed
          </span>
        </div>
      ))}
    </div>
  );
}

export default function CopilotPage() {
  const [query, setQuery] = useState("");
  const [patientId, setPatientId] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [pdfPreview, setPdfPreview] = useState<PdfPreview | null>(null);
  const [previewLoadingId, setPreviewLoadingId] = useState<string | null>(null);

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

  const { data: patients } = useQuery({ queryKey: ["patients"], queryFn: api.patients });
  const { data: history } = useQuery({ queryKey: ["history"], queryFn: api.history });

  // Restore persisted history (oldest first) once per mount.
  useEffect(() => {
    if (history && exchanges.length === 0 && history.length > 0) {
      setExchanges(
        [...history].reverse().map((item) => ({
          id: item.id,
          question: item.query,
          answer: item.answer,
          agents: item.agents_involved,
          toolCalls: item.tool_calls,
          citations: item.citation_report,
          explanation: item.explanation,
        }))
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [history]);

  const patch = (update: Partial<Exchange>) =>
    setExchanges((prev) =>
      prev.map((e, i) => (i === prev.length - 1 ? { ...e, ...update } : e))
    );

  const submit = async () => {
    if (!query.trim() || streaming) return;
    const patient = patients?.find((p) => p.id === patientId);
    const q = query;
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
          context: patient ? { conditions: patient.conditions } : {},
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
      patch({ pending: false, error: "Consultation failed — is the backend running?" });
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-4">
      <div>
        <h1 className="text-xl font-extrabold">Copilot Chat</h1>
        <p className="text-sm text-muted">
          Multi-agent consultation — every citation verified against tool output.
        </p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto">
        {exchanges.length === 0 && (
          <div className="card text-sm text-muted">
            Ask a clinical question, e.g.{" "}
            <em>&ldquo;What is the first-line treatment for hypertension?&rdquo;</em>
          </div>
        )}
        {exchanges.map((exchange, i) => (
          <div key={i} className="space-y-3">
            <div className="ml-auto w-fit max-w-[85%] rounded-2xl bg-primary px-4 py-2.5 text-sm text-white">
              {exchange.question}
            </div>
            <div
              className="max-w-[95%] rounded-2xl border-2 bg-card p-4 text-sm shadow-card"
              style={{ borderImage: "linear-gradient(135deg,#8C92AC,#D1D5DB) 1" }}
            >
              {exchange.pending ? (
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                    Agents working locally…
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
                  <div className="whitespace-pre-wrap leading-relaxed">{exchange.answer}</div>
                  {exchange.citations && <CitationsPanel report={exchange.citations} />}
                  {exchange.explanation && (
                    <ExplainabilityPanel explanation={exchange.explanation} />
                  )}
                  {exchange.toolCalls && exchange.toolCalls.length > 0 && (
                    <div className="rounded-xl bg-surface p-3 text-xs text-muted">
                      <div className="mb-1 flex items-center gap-1 font-semibold">
                        <Wrench size={12} /> Tools used — click a call to inspect it
                      </div>
                      {exchange.toolCalls.map((call, j) => (
                        <ToolCallRow key={j} call={call} />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="card flex items-center gap-2 !p-3">
        <select
          value={patientId}
          onChange={(e) => setPatientId(e.target.value)}
          className="rounded-xl border border-line/70 bg-card px-2 py-2 text-sm"
        >
          <option value="">No patient</option>
          {patients?.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Ask a clinical question…"
          className="min-w-0 flex-1 bg-transparent px-2 text-sm outline-none"
        />
        <button
          onClick={submit}
          disabled={streaming}
          className="rounded-xl bg-primary p-2.5 text-white transition-opacity disabled:opacity-40"
          aria-label="Send"
        >
          <Send size={16} />
        </button>
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
