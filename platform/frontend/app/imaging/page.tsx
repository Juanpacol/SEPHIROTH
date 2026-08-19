"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpenCheck, Bot, CalendarPlus, Eye, Loader2, ScanEye } from "lucide-react";
import { api } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import AgentBadge from "@/components/agent-badge";
import ImageDropzone from "@/components/image-dropzone";
import { OPEN_COPILOT_EVENT } from "@/components/copilot/copilot-widget";
import { useToast } from "@/components/ui/toast";

const modalities = ["xray", "ct", "mri", "ultrasound", "pathology"];

export default function ImagingPage() {
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

  const { data: patients } = useQuery({ queryKey: ["patients"], queryFn: () => api.patients() });

  const analyze = useMutation({
    mutationFn: () => api.analyzeImage({ image_path: imagePath, modality, target }),
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
      showToast("Added to the patient's timeline.");
    },
    onError: () => showToast("Could not add to the timeline.", "error"),
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
      setDescribeError("Could not reach the vision model.");
    } finally {
      setDescribing(false);
    }
  };

  const askSephiroth = () => {
    window.dispatchEvent(
      new CustomEvent(OPEN_COPILOT_EVENT, {
        detail: {
          prefill: `A vision model described this ${modality} image as: "${describeText}"${
            target ? ` (focus: ${target})` : ""
          }. What should I consider clinically, and what evidence supports it?`,
        },
      })
    );
  };

  const hasResult = describeText || describeError || analyze.data;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">Imaging Analysis</h1>
        <p className="text-sm text-muted">
          MONAI-backed analysis + Gemini vision reasoning for X-Ray, CT, MRI, ultrasound and
          pathology images
        </p>
      </div>

      <div className="card space-y-4">
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="mb-1 block text-sm font-semibold">Patient (optional)</label>
            <select
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              className="w-full rounded-xl border border-line/70 bg-card px-3 py-2.5 text-sm"
            >
              <option value="">No patient</option>
              {patients?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="mb-1 flex items-center gap-1.5 text-sm font-semibold">
              Modality
              {modalityAuto && (
                <span className="rounded-full bg-primary-soft px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                  auto-detected
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
            <label className="mb-1 block text-sm font-semibold">Target (optional)</label>
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="e.g. lung, liver"
              className="w-full rounded-xl border border-line/70 px-3 py-2.5 text-sm outline-none focus:border-primary"
            />
          </div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => analyze.mutate()}
            disabled={!imagePath || analyze.isPending}
            className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            <ScanEye size={16} />
            {analyze.isPending ? "Analyzing…" : "Analyze image"}
          </button>
          <button
            onClick={runDescribe}
            disabled={!imagePath || describing}
            className="ai-badge flex items-center gap-2 rounded-xl !px-4 !py-2.5 !text-sm font-semibold disabled:opacity-40"
            aria-label="Describe image with the vision model"
          >
            <Eye size={16} />
            {describing ? "Sampling…" : "Describe with Vision AI"}
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
                <h2 className="font-bold">What this looks like</h2>
                <span className="rounded-full bg-primary-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary">
                  Sample
                </span>
              </div>
              <p className="text-sm text-muted">
                Upload an image on the left and this panel fills in with the same kind of
                streamed vision description and cited evidence shown below — from a real
                consultation, not a mockup.
              </p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/landing/imaging-vision.jpg"
                alt="Example of a completed Imaging Analysis: a streamed vision description alongside cited guideline evidence"
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
                <h2 className="font-bold">Vision description</h2>
                <AgentBadge name="vision-ai" />
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
                  Generated by {describeModel} — describes what's visible only; not a diagnosis.
                </p>
              )}

              {!describing && describeText && (
                <div className="mt-4 flex flex-wrap gap-2 border-t border-line/60 pt-3">
                  <button
                    onClick={() => addToTimeline.mutate()}
                    disabled={!patientId || addToTimeline.isPending || addedToTimeline}
                    title={!patientId ? "Select a patient first" : undefined}
                    className="flex items-center gap-1.5 rounded-xl border border-line/70 px-3 py-2 text-xs font-semibold text-ink/80 hover:bg-surface disabled:opacity-40"
                  >
                    <CalendarPlus size={13} />
                    {addedToTimeline ? "Added to timeline" : addToTimeline.isPending ? "Adding…" : "Add to Timeline"}
                  </button>
                  <button
                    onClick={askSephiroth}
                    className="flex items-center gap-1.5 rounded-xl border border-line/70 px-3 py-2 text-xs font-semibold text-ink/80 hover:bg-surface"
                  >
                    <Bot size={13} />
                    Ask SEPHIROTH
                  </button>
                </div>
              )}
            </div>
          )}

          {(evidence.isPending || (evidence.data && evidence.data.results.length > 0)) && (
            <div className="card">
              <div className="mb-3 flex items-center gap-2">
                <BookOpenCheck size={16} className="text-primary" />
                <h2 className="font-bold">Related guideline evidence</h2>
              </div>
              {evidence.isPending ? (
                <p className="text-sm text-muted">Searching indexed guidelines…</p>
              ) : (
                <div className="space-y-3">
                  {evidence.data!.results.map((r, i) => (
                    <div key={i} className="rounded-xl bg-surface p-3">
                      <p className="text-sm leading-relaxed">{r.content}</p>
                      <p className="mt-1.5 text-xs font-semibold text-primary">{r.citation}</p>
                    </div>
                  ))}
                  <p className="text-xs text-muted">
                    Cited literature about similar findings — not a match to this patient. Verify
                    clinically.
                  </p>
                </div>
              )}
            </div>
          )}

          {analyze.data && (
            <div
              className="card border-2"
              style={{ borderImage: "linear-gradient(135deg,#8C92AC,#D1D5DB) 1" }}
            >
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-bold">Analysis result</h2>
                <AgentBadge name="radiology" />
              </div>
              <pre className="overflow-x-auto rounded-xl bg-surface p-4 text-xs leading-relaxed">
                {JSON.stringify(analyze.data, null, 2)}
              </pre>
              <p className="mt-3 text-xs text-muted">
                Requires professional review — not a diagnosis.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
