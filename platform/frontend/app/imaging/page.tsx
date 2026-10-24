"use client";

/** A stage-and-rail layout: the picture is the biggest thing on screen, on the left; the controls and the
 * AI's own output sit in a narrower rail on the right, in the chat's palette (`.copilot-skin`) — so what the
 * model generated reads as one idiom with the chat and the evidence library, not as a form plus a card. */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenCheck, Bot, CalendarPlus, Clock, Eye, ImageOff, Loader2 } from "lucide-react";
import { api, type RecentImagingAnalysis } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import AgentBadge from "@/components/agent-badge";
import ImageDropzone from "@/components/image-dropzone";
import PatientPicker from "@/components/copilot/patient-picker";
import { OPEN_COPILOT_EVENT } from "@/components/copilot/copilot-widget";
import { useToast } from "@/components/ui/toast";
import PageHeader from "@/components/ui/page-header";
import Sheet from "@/components/ui/sheet";

const PREVIEW_TIMEOUT_MS = 15000;
const TARGET_KEYS = ["lung", "liver", "brain", "heart", "kidney"] as const;

/** `/imaging/preview` requires a JWT Bearer header, which a plain <img src>
 * can never send (browsers don't attach custom headers to image requests) —
 * so the preview is fetched as an authenticated blob and rendered via an
 * object URL instead of pointing <img> at the API path directly. A large
 * study (several MB) on a slow connection can otherwise hang the fetch
 * indefinitely with no visible error, so this also times out and offers a
 * manual retry rather than spinning forever. */
function AuthenticatedPreview({ path, alt }: { path: string; alt: string }) {
  const { t } = useLanguage();
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let url: string | null = null;
    setFailed(false);
    setObjectUrl(null);

    const timeoutId = setTimeout(() => {
      if (!cancelled) setFailed(true);
    }, PREVIEW_TIMEOUT_MS);

    api
      .imagePreviewBlob(path)
      .then((blob) => {
        if (cancelled) return;
        clearTimeout(timeoutId);
        url = URL.createObjectURL(blob);
        setObjectUrl(url);
      })
      .catch(() => {
        clearTimeout(timeoutId);
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
      if (url) URL.revokeObjectURL(url);
    };
  }, [path, attempt]);

  if (failed) {
    return (
      <button
        onClick={() => setAttempt((n) => n + 1)}
        className="flex h-full w-full flex-col items-center justify-center gap-1 text-xs text-muted hover:text-ink"
      >
        <span>{t("imaging.previewFailed")}</span>
        <span className="font-semibold text-primary">{t("common.retry")}</span>
      </button>
    );
  }
  if (!objectUrl) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <Loader2 size={16} className="animate-spin text-muted" />
      </div>
    );
  }
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={objectUrl} alt={alt} className="media-edge h-full w-full object-cover" />;
}

export default function ImagingPage() {
  const { t } = useLanguage();
  const showToast = useToast();
  const queryClient = useQueryClient();
  const [imagePath, setImagePath] = useState("");
  const [target, setTarget] = useState("");
  const [patientId, setPatientId] = useState("");

  const [describeText, setDescribeText] = useState("");
  const [describeModel, setDescribeModel] = useState<string | null>(null);
  const [describeError, setDescribeError] = useState<string | null>(null);
  const [describing, setDescribing] = useState(false);
  const [addedToTimeline, setAddedToTimeline] = useState(false);
  const [expandedAnalysis, setExpandedAnalysis] = useState<RecentImagingAnalysis | null>(null);

  const { data: patients } = useQuery({ queryKey: ["patients"], queryFn: () => api.patients() });
  const { data: demoStudies } = useQuery({
    queryKey: ["imaging-demo"],
    queryFn: () => api.demoImagingStudies(),
    staleTime: Infinity,
  });
  const sample = demoStudies?.[0];
  const { data: recentAnalyses, isLoading: recentLoading } = useQuery({
    queryKey: ["imaging-recent"],
    queryFn: () => api.recentImagingAnalyses(12),
  });

  const evidence = useMutation({ mutationFn: (q: string) => api.searchEvidence(q) });

  const addToTimeline = useMutation({
    mutationFn: () => {
      const modelTag = describeModel ? `[model:${describeModel}] ` : "";
      return api.addTimelineEvent(patientId, {
        type: "imaging",
        title: `Vision description${target ? ` — ${target}` : ""}`,
        detail: `[image_path:${imagePath}] ${modelTag}${describeText}`,
      });
    },
    onSuccess: () => {
      setAddedToTimeline(true);
      showToast(t("imaging.toast.addedToTimeline"));
      queryClient.invalidateQueries({ queryKey: ["imaging-recent"] });
    },
    onError: () => showToast(t("imaging.error.addToTimeline"), "error"),
  });

  const onUploaded = (path: string) => {
    setImagePath(path);
  };

  /** Loads a past analysis's image back into the workspace above so the
   * clinician can re-run the Vision AI description on it — the recent
   * card only ever shows the description text it was generated with. */
  const openInAnalyzer = (a: RecentImagingAnalysis) => {
    if (!a.image_path) {
      showToast(t("imaging.error.noOriginal"), "error");
      return;
    }
    setExpandedAnalysis(null);
    setImagePath(a.image_path);
    setPatientId(a.patient_id);
    setDescribeText("");
    setDescribeError(null);
    setDescribeModel(null);
    setAddedToTimeline(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
    showToast(t("imaging.toast.loadedIntoWorkspace").replace("{button}", t("imaging.describeVisionAi")));
  };

  const runDescribe = async () => {
    if (!imagePath || describing) return;
    setDescribing(true);
    setDescribeError(null);
    setDescribeText("");
    setDescribeModel(null);
    setAddedToTimeline(false);
    evidence.reset();

    try {
      const res = await fetch("/api/medical/imaging/describe/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ image_path: imagePath, clinical_focus: target }),
      });
      if (!res.ok || !res.body) throw new Error(`${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";

        for (const chunk of chunks) {
          if (!chunk.startsWith("data: ")) continue;
          const event = JSON.parse(chunk.slice(6));

          if (event.event === "chunk") {
            fullText += event.text;
            setDescribeText((prev) => prev + event.text);
          } else if (event.event === "final") {
            setDescribeModel(event.model ?? null);
            // Grounds the description against real, citable guideline text
            // instead of asserting a diagnosis — same RAG endpoint /evidence
            // uses, just fed the vision description as its query.
            evidence.mutate(fullText);
          } else if (event.event === "error") {
            setDescribeError(event.detail);
          }
        }
      }
    } catch {
      setDescribeError(t("imaging.error.visionUnreachable"));
    } finally {
      setDescribing(false);
    }
  };

  const askSephiroth = () => {
    const focus = target ? t("imaging.askPrefillFocus").replace("{target}", target) : "";
    window.dispatchEvent(
      new CustomEvent(OPEN_COPILOT_EVENT, {
        detail: {
          prefill: t("imaging.askPrefill").replace("{description}", describeText).replace("{focus}", focus),
        },
      })
    );
  };

  const hasResult = describeText || describeError;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader eyebrow={t("patients.eyebrow")} title={t("nav.imaging")} subtitle={t("imaging.subtitle")} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* The stage — the picture, as big as the page allows. */}
        <div className="lg:col-span-8">
          <div className="card min-h-[320px] !p-3 lg:min-h-[480px]">
            <ImageDropzone onUploaded={onUploaded} />
          </div>
        </div>

        {/* The rail — who/what, then what the model made of it. */}
        <div className="space-y-4 lg:col-span-4">
          <div className="card space-y-3">
            <div>
              <label className="eyebrow mb-1.5 block text-muted">{t("imaging.patientOptional")}</label>
              <PatientPicker
                placement="down"
                patients={patients ?? []}
                value={patientId}
                onChange={setPatientId}
                noneLabel={t("copilot.noPatient")}
              />
            </div>
            <div>
              <label className="eyebrow mb-1.5 block text-muted">{t("imaging.targetOptional")}</label>
              <input
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder={t("imaging.targetPlaceholder")}
                className="input py-2"
              />
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {TARGET_KEYS.map((key) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() =>
                      setTarget((cur) =>
                        cur === t(`imaging.target.${key}`) ? "" : t(`imaging.target.${key}`)
                      )
                    }
                    className={`tap rounded-full border px-2.5 py-1 text-xs transition-colors duration-normal ${
                      target === t(`imaging.target.${key}`)
                        ? "border-primary-ink/60 bg-primary-soft/60 text-ink"
                        : "border-line/60 text-muted hover:border-line hover:text-ink"
                    }`}
                  >
                    {t(`imaging.target.${key}`)}
                  </button>
                ))}
              </div>
            </div>
            <button
              onClick={runDescribe}
              disabled={!imagePath || describing}
              className="btn-primary tap w-full justify-center"
              aria-label={t("imaging.describeAria")}
            >
              <Eye size={16} />
              {describing ? t("imaging.sampling") : t("imaging.describeVisionAi")}
            </button>
          </div>

          {!hasResult && !describing && (
            <div className="card space-y-2">
              <div className="flex items-center gap-2">
                <Eye size={14} strokeWidth={1.5} className="text-muted" />
                <h2 className="eyebrow text-muted">{t("imaging.whatThisLooksLike")}</h2>
                <span className="eyebrow ml-auto text-primary-ink">{t("imaging.sample")}</span>
              </div>
              <p className="text-xs text-muted">{t("imaging.sampleDescription")}</p>
              {sample ? (
                <div className="space-y-2.5" data-testid="imaging-sample">
                  <div className="aspect-[4/3] w-full overflow-hidden rounded-inner bg-surface">
                    <AuthenticatedPreview path={sample.image} alt={`${sample.modality} ${sample.region}`} />
                  </div>
                  <p className="line-clamp-5 text-xs leading-relaxed text-ink/80">{sample.description}</p>
                  <p className="font-mono text-[10px] text-muted">
                    {t("imaging.modelLabel").replace("{model}", sample.model)}
                  </p>
                </div>
              ) : null}
            </div>
          )}

          {(describing || describeText || describeError) && (
            <div className="copilot-skin animate-answer-in rounded-squircle p-4 ring-1 ring-white/15">
              <div className="mb-2 flex items-center justify-between">
                <h2 className="font-display text-lg font-light uppercase leading-none tracking-wide">
                  {t("imaging.visionDescription")}
                </h2>
                <AgentBadge name={t("imaging.visionAiBadge")} />
              </div>
              {describeError ? (
                <p className="text-sm text-danger">{describeError}</p>
              ) : (
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink/90">
                  {describeText}
                  {describing && (
                    <Loader2 size={13} className="ml-1 inline animate-spin align-middle text-muted" />
                  )}
                </p>
              )}
              {describeModel && (
                <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.1em] text-muted">
                  {t("imaging.generatedByDisclaimer").replace("{model}", describeModel)}
                </p>
              )}

              {!describing && describeText && (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-white/10 pt-3">
                  <button
                    onClick={() => addToTimeline.mutate()}
                    disabled={!patientId || addToTimeline.isPending || addedToTimeline}
                    title={!patientId ? t("imaging.selectPatientFirst") : undefined}
                    className="tap inline-flex items-center gap-1.5 rounded-full border border-white/15 px-2.5 py-1.5 text-xs font-medium text-ink/80 transition-colors duration-normal hover:border-white/30 hover:bg-white/10 disabled:opacity-40"
                  >
                    <CalendarPlus size={13} />
                    {addedToTimeline
                      ? t("imaging.addedToTimeline")
                      : addToTimeline.isPending
                        ? t("imaging.addingToTimeline")
                        : t("imaging.addToTimeline")}
                  </button>
                  <button
                    onClick={askSephiroth}
                    className="tap inline-flex items-center gap-1.5 rounded-full border border-white/15 px-2.5 py-1.5 text-xs font-medium text-ink/80 transition-colors duration-normal hover:border-white/30 hover:bg-white/10"
                  >
                    <Bot size={13} />
                    {t("imaging.askSephiroth")}
                  </button>
                </div>
              )}
            </div>
          )}

          {(evidence.isPending || (evidence.data && evidence.data.results.length > 0)) && (
            <div className="copilot-skin rounded-squircle p-4 ring-1 ring-white/15">
              <div className="mb-2 flex items-center gap-2">
                <BookOpenCheck size={14} strokeWidth={1.5} className="text-primary-ink" />
                <h2 className="eyebrow text-muted">{t("imaging.relatedEvidence")}</h2>
              </div>
              {evidence.isPending ? (
                <p className="text-sm text-muted">{t("imaging.searchingGuidelines")}</p>
              ) : (
                <div className="space-y-3">
                  {evidence.data!.results.map((r, i) => (
                    <div key={i} className="border-t border-white/10 pt-3 first:border-0 first:pt-0">
                      <p className="text-sm leading-relaxed text-ink/90">{r.content}</p>
                      <p className="mt-1.5 text-xs font-semibold text-primary-ink">{r.citation}</p>
                    </div>
                  ))}
                  <p className="text-[11px] text-muted">{t("imaging.evidenceDisclaimer")}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Clock size={13} strokeWidth={1.5} className="text-primary-ink" />
          <h2 className="eyebrow text-muted">{t("imaging.recentAnalyses")}</h2>
          <span className="eyebrow ml-1 text-primary-ink">{t("imaging.aiGenerated")}</span>
        </div>

        {recentLoading && <p className="text-sm text-muted">{t("imaging.loadingRecent")}</p>}

        {!recentLoading && (!recentAnalyses || recentAnalyses.length === 0) && (
          <div className="card">
            <p className="text-sm text-muted">{t("imaging.noneYet")}</p>
          </div>
        )}

        {!recentLoading && recentAnalyses && recentAnalyses.length > 0 && (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            {recentAnalyses.map((a, i) => (
              <div
                key={a.id}
                style={{ animationDelay: `${Math.min(i, 9) * 45}ms` }}
                className="card flex animate-fadeIn flex-col gap-2.5 !p-3 [animation-fill-mode:both]"
              >
                <div className="aspect-square w-full overflow-hidden rounded-inner bg-surface">
                  {a.image_path ? (
                    <AuthenticatedPreview path={a.image_path} alt={a.title} />
                  ) : (
                    <div
                      className="flex h-full w-full flex-col items-center justify-center gap-1 px-4 text-center text-xs text-muted"
                      data-testid="preview-unavailable"
                    >
                      <ImageOff size={18} aria-hidden="true" />
                      <span className="font-semibold">{t("imaging.unavailable")}</span>
                      <span>{t(`imaging.unavailable.${a.preview_unavailable ?? "no_image"}`)}</span>
                    </div>
                  )}
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="min-w-0 truncate text-sm font-semibold">{a.title}</p>
                    <span className="shrink-0 whitespace-nowrap font-mono text-[10px] text-muted">
                      {a.date}
                    </span>
                  </div>
                  <p className="font-mono text-[11px] text-primary-ink">{a.patient_name}</p>
                  <p className="line-clamp-3 text-xs leading-relaxed text-ink/80">{a.description}</p>
                </div>
                <div className="flex gap-2 border-t border-line/50 pt-2">
                  <button
                    onClick={() => setExpandedAnalysis(a)}
                    className="tap flex-1 rounded-lg border border-line/60 px-2 py-1.5 text-xs font-semibold text-ink/80 hover:bg-primary-soft/30"
                  >
                    {t("imaging.viewFull")}
                  </button>
                  <button
                    onClick={() => openInAnalyzer(a)}
                    disabled={!a.image_path}
                    className="btn-primary tap flex-1 justify-center !py-1.5 text-xs disabled:opacity-40"
                  >
                    {t("imaging.analyzePrecisely")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Sheet
        open={expandedAnalysis !== null}
        onClose={() => setExpandedAnalysis(null)}
        side="right"
        title={expandedAnalysis?.title ?? ""}
      >
        {expandedAnalysis && (
          <div className="space-y-4">
            <div>
              <p className="font-mono text-[11px] text-primary-ink">{expandedAnalysis.patient_name}</p>
              <p className="font-mono text-[10px] text-muted">{expandedAnalysis.date}</p>
            </div>

            {expandedAnalysis.image_path && (
              <div className="max-h-80 overflow-hidden rounded-xl bg-surface">
                <AuthenticatedPreview path={expandedAnalysis.image_path} alt={expandedAnalysis.title} />
              </div>
            )}

            <p className="whitespace-pre-wrap text-sm leading-relaxed">{expandedAnalysis.description}</p>
            {expandedAnalysis.model && (
              <p className="text-xs text-muted">
                {t("imaging.generatedByDisclaimer").replace("{model}", expandedAnalysis.model)}
              </p>
            )}

            <button
              onClick={() => openInAnalyzer(expandedAnalysis)}
              disabled={!expandedAnalysis.image_path}
              className="btn-primary tap w-full justify-center disabled:opacity-40"
            >
              <Eye size={16} />
              {t("imaging.runPreciseAnalysis")}
            </button>
          </div>
        )}
      </Sheet>
    </div>
  );
}
