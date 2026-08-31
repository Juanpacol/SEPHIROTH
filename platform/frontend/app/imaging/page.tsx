"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpenCheck, Bot, CalendarPlus, Clock, Eye, Loader2 } from "lucide-react";
import { api, type RecentImagingAnalysis } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { useLanguage } from "@/lib/language";
import AgentBadge from "@/components/agent-badge";
import ImageDropzone from "@/components/image-dropzone";
import { OPEN_COPILOT_EVENT } from "@/components/copilot/copilot-widget";
import { useToast } from "@/components/ui/toast";

const modalities = ["xray", "ct", "mri", "ultrasound", "pathology"];

const PREVIEW_TIMEOUT_MS = 15000;

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
  return <img src={objectUrl} alt={alt} className="h-full w-full object-cover" />;
}

export default function ImagingPage() {
  const { t } = useLanguage();
  const showToast = useToast();
  const [imagePath, setImagePath] = useState("");
  const [modality, setModality] = useState("xray");
  const [modalityAuto, setModalityAuto] = useState(false);
  const [target, setTarget] = useState("");
  const [patientId, setPatientId] = useState("");

  const [describeText, setDescribeText] = useState("");
  const [describeModel, setDescribeModel] = useState<string | null>(null);
  const [describeError, setDescribeError] = useState<string | null>(null);
  const [describing, setDescribing] = useState(false);
  const [addedToTimeline, setAddedToTimeline] = useState(false);
  const [expandedAnalysis, setExpandedAnalysis] = useState<RecentImagingAnalysis | null>(null);

  const { data: patients } = useQuery({ queryKey: ["patients"], queryFn: () => api.patients() });
  const { data: recentAnalyses, isLoading: recentLoading } = useQuery({
    queryKey: ["imaging-recent"],
    queryFn: () => api.recentImagingAnalyses(12),
  });

  const evidence = useMutation({ mutationFn: (q: string) => api.searchEvidence(q) });

  const addToTimeline = useMutation({
    mutationFn: () =>
      api.addTimelineEvent(patientId, {
        type: "imaging",
        title: `${modality.toUpperCase()} vision description${target ? ` — ${target}` : ""}`,
        detail: describeText,
      }),
    onSuccess: () => {
      setAddedToTimeline(true);
      showToast(t("imaging.toast.addedToTimeline"));
    },
    onError: () => showToast(t("imaging.error.addToTimeline"), "error"),
  });

  const onUploaded = async (path: string) => {
    setImagePath(path);
    setModalityAuto(false);
    if (!path) return;
    try {
      const { modality: guess } = await api.detectModality(path);
      if (guess && guess !== "unknown") {
        setModality(guess);
        setModalityAuto(true);
      }
    } catch {
      // Best-effort only — the clinician can always pick the modality by hand.
    }
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
    const guess = a.title.split(" ")[0].toLowerCase();
    if (modalities.includes(guess)) {
      setModality(guess);
      setModalityAuto(false);
    }
    setDescribeText("");
    setDescribeError(null);
    setDescribeModel(null);
    setAddedToTimeline(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
    showToast(
      t("imaging.toast.loadedIntoWorkspace").replace("{button}", t("imaging.describeVisionAi"))
    );
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
          prefill: t("imaging.askPrefill")
            .replace("{modality}", modality)
            .replace("{description}", describeText)
            .replace("{focus}", focus),
        },
      })
    );
  };

  const hasResult = describeText || describeError;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("nav.imaging")}</h1>
        <p className="text-sm text-muted">{t("imaging.subtitle")}</p>
      </div>

      <div className="card space-y-4">
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="mb-1 block text-sm font-semibold">{t("imaging.patientOptional")}</label>
            <select
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              className="w-full rounded-xl border border-line/70 bg-card px-3 py-2.5 text-sm"
            >
              <option value="">{t("copilot.noPatient")}</option>
              {patients?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
              {t("imaging.modality")}
              {modalityAuto && (
                <span className="rounded-full bg-primary-soft px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                  {t("imaging.autoDetected")}
                </span>
              )}
            </label>
            <select
              value={modality}
              onChange={(e) => {
                setModality(e.target.value);
                setModalityAuto(false);
              }}
              className="w-full rounded-xl border border-line/70 bg-card px-3 py-2.5 text-sm"
            >
              {modalities.map((m) => (
                <option key={m} value={m}>
                  {m.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-sm font-semibold">{t("imaging.targetOptional")}</label>
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder={t("imaging.targetPlaceholder")}
              className="w-full rounded-xl border border-line/70 px-3 py-2.5 text-sm outline-none focus:border-primary"
            />
          </div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={runDescribe}
            disabled={!imagePath || describing}
            className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
            aria-label={t("imaging.describeAria")}
          >
            <Eye size={16} />
            {describing ? t("imaging.sampling") : t("imaging.describeVisionAi")}
          </button>
        </div>
      </div>

      {/* Left: add-file control + preview stacked. Right: AI findings, streamed live. */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <div className="card !p-3">
            <ImageDropzone onUploaded={onUploaded} />
          </div>
        </div>

        <div className="space-y-4">
          {!hasResult && !describing && (
            <div className="card space-y-3">
              <div className="flex items-center gap-2">
                <Eye size={16} className="text-primary" />
                <h2 className="font-bold">{t("imaging.whatThisLooksLike")}</h2>
                <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                  {t("imaging.sample")}
                </span>
              </div>
              <p className="text-sm text-muted">{t("imaging.sampleDescription")}</p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/landing/imaging-vision.jpg"
                alt={t("imaging.sampleAlt")}
                className="w-full rounded-xl border border-line/60"
              />
            </div>
          )}

          {(describing || describeText || describeError) && (
            <div
              className="card border-2"
              style={{ borderImage: "linear-gradient(135deg,#8C92AC,#D1D5DB) 1" }}
            >
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-bold">{t("imaging.visionDescription")}</h2>
                <AgentBadge name={t("imaging.visionAiBadge")} />
              </div>
              {describeError ? (
                <p className="text-sm text-danger">{describeError}</p>
              ) : (
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {describeText}
                  {describing && (
                    <Loader2 size={13} className="ml-1 inline animate-spin align-middle text-muted" />
                  )}
                </p>
              )}
              {describeModel && (
                <p className="mt-3 text-xs text-muted">
                  {t("imaging.generatedByDisclaimer").replace("{model}", describeModel)}
                </p>
              )}

              {!describing && describeText && (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-line/60 pt-3">
                  <button
                    onClick={() => addToTimeline.mutate()}
                    disabled={!patientId || addToTimeline.isPending || addedToTimeline}
                    title={!patientId ? t("imaging.selectPatientFirst") : undefined}
                    className="flex items-center gap-1.5 rounded-xl border border-line/70 px-3 py-2 text-xs font-semibold text-ink/80 hover:bg-surface disabled:opacity-40"
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
                    className="flex items-center gap-1.5 rounded-xl border border-line/70 px-3 py-2 text-xs font-semibold text-ink/80 hover:bg-surface"
                  >
                    <Bot size={13} />
                    {t("imaging.askSephiroth")}
                  </button>
                </div>
              )}
            </div>
          )}

          {(evidence.isPending || (evidence.data && evidence.data.results.length > 0)) && (
            <div className="card">
              <div className="mb-3 flex items-center gap-2">
                <BookOpenCheck size={16} className="text-primary" />
                <h2 className="font-bold">{t("imaging.relatedEvidence")}</h2>
              </div>
              {evidence.isPending ? (
                <p className="text-sm text-muted">{t("imaging.searchingGuidelines")}</p>
              ) : (
                <div className="space-y-3">
                  {evidence.data!.results.map((r, i) => (
                    <div key={i} className="rounded-xl bg-surface p-3">
                      <p className="text-sm leading-relaxed">{r.content}</p>
                      <p className="mt-1.5 text-xs font-semibold text-primary">{r.citation}</p>
                    </div>
                  ))}
                  <p className="text-xs text-muted">{t("imaging.evidenceDisclaimer")}</p>
                </div>
              )}
            </div>
          )}

        </div>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Clock size={16} className="text-primary" />
          <h2 className="text-base font-bold">{t("imaging.recentAnalyses")}</h2>
          <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
            {t("imaging.aiGenerated")}
          </span>
        </div>

        {recentLoading && <p className="text-sm text-muted">{t("imaging.loadingRecent")}</p>}

        {!recentLoading && (!recentAnalyses || recentAnalyses.length === 0) && (
          <div className="card">
            <p className="text-sm text-muted">{t("imaging.noneYet")}</p>
          </div>
        )}

        {!recentLoading && recentAnalyses && recentAnalyses.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recentAnalyses.map((a) => (
              <div key={a.id} className="card flex flex-col gap-3 !p-3">
                <div className="aspect-square w-full overflow-hidden rounded-lg bg-surface">
                  {a.image_path ? (
                    <AuthenticatedPreview path={a.image_path} alt={a.title} />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-xs text-muted">
                      {t("imaging.noPreview")}
                    </div>
                  )}
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-bold">{a.title}</p>
                    <span className="whitespace-nowrap text-[10px] text-muted">{a.date}</span>
                  </div>
                  <p className="text-xs font-semibold text-primary">{a.patient_name}</p>
                  <p className="line-clamp-4 text-xs leading-relaxed text-ink/80">{a.description}</p>
                  {a.model && (
                    <p className="text-[10px] text-muted">
                      {t("imaging.modelLabel").replace("{model}", a.model)}
                    </p>
                  )}
                </div>
                <div className="flex gap-2 border-t border-line/60 pt-2">
                  <button
                    onClick={() => setExpandedAnalysis(a)}
                    className="flex-1 rounded-lg border border-line/70 px-2 py-1.5 text-xs font-semibold text-ink/80 hover:bg-surface"
                  >
                    {t("imaging.viewFull")}
                  </button>
                  <button
                    onClick={() => openInAnalyzer(a)}
                    disabled={!a.image_path}
                    className="flex-1 rounded-lg bg-primary px-2 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
                  >
                    {t("imaging.analyzePrecisely")}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {expandedAnalysis && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => setExpandedAnalysis(null)}
        >
          <div
            className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-card p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <h2 className="font-bold">{expandedAnalysis.title}</h2>
                <p className="text-xs font-semibold text-primary">{expandedAnalysis.patient_name}</p>
                <p className="text-[10px] text-muted">{expandedAnalysis.date}</p>
              </div>
              <button
                onClick={() => setExpandedAnalysis(null)}
                className="rounded-lg border border-line/70 px-2 py-1 text-xs font-semibold text-ink/80 hover:bg-surface"
              >
                {t("common.close")}
              </button>
            </div>

            {expandedAnalysis.image_path && (
              <div className="mb-4 max-h-80 overflow-hidden rounded-xl bg-surface">
                <AuthenticatedPreview path={expandedAnalysis.image_path} alt={expandedAnalysis.title} />
              </div>
            )}

            <p className="whitespace-pre-wrap text-sm leading-relaxed">{expandedAnalysis.description}</p>
            {expandedAnalysis.model && (
              <p className="mt-3 text-xs text-muted">
                {t("imaging.generatedByDisclaimer").replace("{model}", expandedAnalysis.model)}
              </p>
            )}

            <div className="mt-4 border-t border-line/60 pt-3">
              <button
                onClick={() => openInAnalyzer(expandedAnalysis)}
                disabled={!expandedAnalysis.image_path}
                className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
              >
                <Eye size={16} />
                {t("imaging.runPreciseAnalysis")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
