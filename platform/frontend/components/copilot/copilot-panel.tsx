"use client";

/** The Copilot Chat conversation itself — extracted verbatim from the old
 * dedicated `/copilot` page so it can be dropped into the floating
 * `CopilotWidget` (mounted app-wide in AppShell) instead of requiring a
 * navigation away from whatever the clinician was looking at. No page-level
 * chrome (h1/subtitle) here; the widget's own header carries that. */

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download, Loader2, Send, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { api, type CitationReport, type Explanation, type LLMCall, type ToolCall } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import AgentBadge from "@/components/agent-badge";
import { agentLabel } from "@/lib/agents";
import WingMark from "@/components/brand/wing-mark";
import PatientPicker from "@/components/copilot/patient-picker";
import AnswerText from "@/components/copilot/answer-text";
import AnswerRating from "@/components/answer-rating";
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
  /** From the final event's trace: which provider/model served each call. */
  llmCalls?: LLMCall[];
  traceId?: string;
  progress?: AgentProgress[];
  pending?: boolean;
  /** Which silent leg of the pipeline is running right now — surfaced as a
   * one-line status instead of a single opaque "agents working" blob, since
   * `agent_completed` only fires once (one specialist, ADR-016) and leaves
   * the longest, least-visible leg (claim verification) with no signal of
   * its own otherwise. */
  stage?: "routing" | "answering" | "verifying";
  /** The answer is still being written out; what hangs off it (citations, trace, rating) waits. */
  revealing?: boolean;
  /** True once any non-reset `answer_delta` arrived for this exchange — real
   * token streaming (AB#67). When true, `final` sets the answer directly
   * instead of running the word-by-word `revealAnswer` reveal. */
  streamedAnswer?: boolean;
  error?: string;
}

/** Suggested starter questions — kept in English regardless of UI locale,
 * matching the clinical literature/citations the agents cite.
 *
 * Kept to 3, one per answering path, rather than an exhaustive tour of the
 * corpus — a long row of buttons read as "pick the right one" instead of
 * "here's the kind of thing this can do". Every one was verified with
 * `RAGPipeline().retrieve(query)` (keyword-only, no API key) to actually
 * surface a corpus document with >=2 distinct shared tokens — the tokenizer
 * does no stemming, so e.g. "dosing" vs "dose" or "recognized" vs
 * "recognition" is enough to silently drop below the match floor even when
 * the topic exists in the corpus. A suggested question the corpus can't
 * answer abstains, which reads as the product being broken rather than as
 * it being careful. `warfarinIbuprofen` routes to the drug-safety agent
 * rather than RAG evidence, so the set still exercises both answering
 * paths despite the smaller count. */
/** The query text sent to the backend/RAG corpus always stays the English
 * original (`query`) regardless of UI language — the corpus match described
 * above was verified against these exact English strings. `labelKey` is
 * only what the button displays. */
const SUGGESTED_QUESTIONS = [
  {
    query: "What blood pressure reading is considered high?",
    labelKey: "copilot.suggested.bloodPressure",
  },
  {
    query: "What is the A1C target for adults with type 2 diabetes?",
    labelKey: "copilot.suggested.a1cTarget",
  },
  {
    query: "Do warfarin and ibuprofen interact?",
    labelKey: "copilot.suggested.warfarinIbuprofen",
  },
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

function reportSectionKeys(exchange: Exchange): string[] {
  const citationCount =
    (exchange.citations?.verified?.length ?? 0) + (exchange.citations?.fabricated?.length ?? 0);
  return [
    "copilot.report.clinicalQaAndResponse",
    exchange.agents?.length ? "copilot.report.agentsInvolved" : null,
    citationCount > 0 ? "copilot.citationGuard" : null,
    exchange.explanation?.steps.length ? "copilot.report.reasoningTrace" : null,
    "copilot.report.disclaimer",
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
        className="flex max-h-[90dvh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-card shadow-raised"
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
            aria-label={t("copilot.closePreview")}
            className="rounded-full p-1.5 text-muted hover:bg-surface"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-hidden bg-surface">
          <iframe src={preview.url} title={t("copilot.pdfPreview")} className="h-[50dvh] w-full" />
        </div>

        <div className="border-t border-line/60 p-4">
          <p className="mb-2 eyebrow text-muted">{t("copilot.includedSections")}</p>
          <ul className="mb-4 space-y-1">
            {preview.sections.map((section) => (
              <li key={section} className="flex items-center gap-1.5 text-sm">
                <CheckCircle2 size={13} className="text-success" /> {t(section)}
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
  // Tracks the in-flight /consult/stream fetch so a new submit (or an
  // unmount) can abort it. Without this the browser never closes the old
  // connection, the backend's StreamingResponse disconnect-cancellation
  // (which otherwise frees the Ollama slot in <1s, see AB#78) never fires,
  // and the old consultation keeps running to completion in the background —
  // contending for the single-concurrency Ollama slot with whatever runs
  // next (observed live: AB#67 verification).
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortControllerRef.current?.abort(), []);

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
        sections: reportSectionKeys(exchange),
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

  const { data: patients } = useQuery({
    queryKey: ["patients"],
    queryFn: () => api.patients(),
  });

  const patch = (update: Partial<Exchange>) =>
    setExchanges((prev) => prev.map((e, i) => (i === prev.length - 1 ? { ...e, ...update } : e)));

  /** Used only when no `answer_delta` streamed for this exchange (the fast
   * path, or a provider without real token streaming today — Gemini, Groq,
   * Ollama's OpenAI-compatible path; see AB#67). The `final` SSE event
   * carries the whole answer in one shot in that case, so revealing it
   * word-by-word client-side is what gives the "the system is producing
   * this" feel instead of a wall of text appearing instantly. Runs detached
   * from the SSE read loop so it doesn't hold up later events (`persisted`).
   * When a real stream did arrive, `final` sets the answer directly instead
   * — see the `answer_delta`/`final` handling in `submit` below. */
  const revealAnswer = (fullAnswer: string) => {
    const words = fullAnswer.split(" ");
    let shown = 0;
    const step = () => {
      shown = Math.min(shown + 3, words.length);
      const done = shown >= words.length;
      patch({ answer: words.slice(0, shown).join(" "), revealing: !done });
      if (!done) setTimeout(step, 30);
    };
    step();
  };

  const submit = async (override?: string) => {
    const text = override ?? query;
    if (!text.trim() || streaming) return;
    const patient = patients?.find((p) => p.id === patientId);
    const q = text;
    setQuery("");
    setStreaming(true);
    setExchanges((prev) => [...prev, { question: q, pending: true, progress: [], stage: "routing" }]);

    // Abort whatever the previous submit (or a lingering nav away) left
    // in flight before starting this one — see abortControllerRef above.
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    // A newer submit may abort `controller` and move `abortControllerRef`
    // on before this fetch's callbacks run; those must no-op rather than
    // patch whatever exchange is now last in the array.
    const isStale = () => abortControllerRef.current !== controller;

    try {
      const res = await fetch("/api/agents/consult/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          query: q,
          patient_id: patientId,
          context: {
            ...(patient ? { conditions: patient.conditions } : {}),
            language: lang,
          },
        }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      // Local to this turn, not React state — `final`'s handler needs to
      // know synchronously whether a delta already streamed, and reading
      // `exchanges` here would close over the pre-submit snapshot rather
      // than what the `answer_delta` branch below has been setting.
      let streamedThisTurn = false;

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
              stage: "answering",
            });
          } else if (event.event === "answer_delta") {
            // Additive, provisional (AB#67) — batches already include
            // spaces, so they're appended verbatim, never trimmed.
            streamedThisTurn = true;
            setExchanges((prev) =>
              prev.map((e, i) =>
                i === prev.length - 1
                  ? {
                      ...e,
                      // `pending` must clear here too, not just on `final` —
                      // the pending/progress view is a different branch from
                      // the answer view (below), so the provisional text
                      // from here on only renders once this flips.
                      pending: false,
                      answer: event.reset ? "" : (e.answer ?? "") + (event.text as string),
                      streamedAnswer: true,
                      revealing: true,
                    }
                  : e
              )
            );
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
                      stage: "verifying",
                    }
                  : e
              )
            );
          } else if (event.event === "final") {
            const streamed = streamedThisTurn;
            patch({
              pending: false,
              revealing: streamed ? false : true,
              answer: streamed ? (event.answer as string) : "",
              agents: event.agents_involved,
              toolCalls: event.tool_calls,
              citations: event.citation_report,
              explanation: event.explanation,
              llmCalls: (event.trace?.llm_calls as LLMCall[] | undefined) ?? [],
              traceId: event.trace?.trace_id as string | undefined,
            });
            // No fake reveal when deltas already streamed in the answer —
            // `final.answer` is set directly above instead (AB#67).
            if (!streamed) revealAnswer(event.answer as string);
          } else if (event.event === "persisted") {
            patch({ id: event.id });
          } else if (event.event === "error") {
            patch({ pending: false, revealing: false, answer: undefined, error: event.detail });
          }
        }
      }
    } catch (err) {
      // A newer submit's abort() rejects this fetch/reader with AbortError —
      // expected, not a failure, and by the time it lands `prev.length - 1`
      // is the newer exchange, so patching here would corrupt it.
      if (isStale() || (err instanceof DOMException && err.name === "AbortError")) return;
      patch({ pending: false, revealing: false, answer: undefined, error: t("copilot.failed") });
    } finally {
      if (!isStale()) setStreaming(false);
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
                  key={q.query}
                  onClick={() => submit(q.query)}
                  disabled={streaming}
                  className="rounded-full border border-line/70 bg-card px-3 py-1.5 text-xs font-medium text-ink/80 transition-colors hover:border-primary hover:text-primary disabled:opacity-40"
                >
                  {t(q.labelKey)}
                </button>
              ))}
            </div>
          </div>
        )}
        {exchanges.map((exchange, i) => (
          <div key={i} className="space-y-3">
            <div className="ml-auto w-fit max-w-[85%] rounded-2xl border border-white/30 bg-white/15 px-4 py-2.5 text-sm text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.3)] backdrop-blur-sm">
              {exchange.question}
            </div>
            {/* No `ai-ring` here: its 2px #8c92ac halo read as a stray light
                border around every answer. The AI-provenance signal that ring
                carried (design decision #4) still ships on each answer via
                AgentBadge, which uses the same Sephiroth gradient. */}
            <div className="max-w-[95%] rounded-squircle bg-card/80 p-4 text-sm ring-1 ring-white/10">
              {exchange.pending ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <WingMark size={14} className="text-primary-ink motion-safe:animate-pulse" />
                    <span className="eyebrow text-muted">{t(`copilot.stage.${exchange.stage ?? "routing"}`)}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {exchange.progress?.map((agent) => (
                      <span
                        key={`${agent.name}-${agent.done}`}
                        role="status"
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
                          agent.done ? "ai-badge animate-chip-pop" : "animate-chip-in bg-surface text-muted"
                        }`}
                      >
                        {agent.done ? <CheckCircle2 size={11} /> : <ThinkingDots />}
                        {agentLabel(agent.name, t)}
                        {agent.toolCalls.length > 0 && ` · ${agent.toolCalls.map((t) => t.name).join(", ")}`}
                      </span>
                    ))}
                  </div>
                  <div aria-hidden className="h-px w-full overflow-hidden rounded-full bg-white/10">
                    <div className="h-full w-1/3 animate-sheen bg-[linear-gradient(90deg,transparent,#b6cfff,transparent)]" />
                  </div>
                </div>
              ) : exchange.error ? (
                <span className="text-danger">{exchange.error}</span>
              ) : (
                <div className="animate-answer-in space-y-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {exchange.agents?.map((agent) => (
                      <AgentBadge key={agent} name={agentLabel(agent, t)} />
                    ))}
                    {exchange.id && (
                      <button
                        onClick={() => openPdfPreview(exchange)}
                        disabled={previewLoadingId === exchange.id}
                        aria-label={t("copilot.previewExportPdf")}
                        title={t("copilot.exportPdf")}
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
                  {/* What hangs off the answer waits until it has been written out, then comes in. */}
                  {!exchange.revealing && (
                    <div className="animate-answer-in space-y-3">
                      {exchange.citations && (
                        <CitationsPanel report={exchange.citations} toolCalls={exchange.toolCalls} />
                      )}
                      {exchange.explanation && (
                        <ExplainabilityPanel
                          explanation={exchange.explanation}
                          llmCalls={exchange.llmCalls}
                          traceId={exchange.traceId}
                        />
                      )}
                      {exchange.id && <AnswerRating key={exchange.id} consultationId={exchange.id} />}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* `shrink-0`: the transcript above is `flex-1` and must give up the
          space, never the composer. */}
      <div
        className={`flex shrink-0 cursor-text flex-col rounded-squircle bg-card/80 ring-1 ring-white/15 backdrop-blur-sm transition-all duration-200 ${
          inputFocused ? "!ring-primary-ink/60" : ""
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
          onFocus={(e) => {
            setInputFocused(true);
            // iOS shrinks the visual viewport for the keyboard but leaves the
            // layout viewport alone, so a composer pinned to the bottom of a
            // full-screen panel ends up behind it. Scrolling the field into
            // view is the part of that WebKit has no other answer for.
            requestAnimationFrame(() => e.target.scrollIntoView({ block: "center" }));
          }}
          onBlur={() => setInputFocused(false)}
          placeholder={t("copilot.placeholder")}
          rows={1}
          className="max-h-40 min-h-[44px] w-full resize-none bg-transparent px-4 pt-3 text-sm leading-relaxed focus-visible:!outline-none placeholder:text-muted"
        />
        <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5 pt-1.5">
          <PatientPicker
            patients={patients ?? []}
            value={patientId}
            onChange={setPatientId}
            noneLabel={t("copilot.noPatient")}
          />
          <button
            onClick={() => submit()}
            disabled={streaming || !query.trim()}
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
              query.trim() && !streaming ? "bg-white/15 text-primary-ink" : "bg-surface/60 text-muted"
            } disabled:cursor-not-allowed`}
            aria-label={t("copilot.send")}
          >
            {streaming ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          </button>
        </div>
      </div>

      {pdfPreview && (
        <PdfPreviewModal preview={pdfPreview} onClose={closePdfPreview} onConfirm={confirmPdfDownload} />
      )}
    </div>
  );
}
