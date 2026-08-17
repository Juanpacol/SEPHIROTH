"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Eye, Loader2, ScanEye } from "lucide-react";
import { api } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import AgentBadge from "@/components/agent-badge";
import ImageDropzone from "@/components/image-dropzone";

const modalities = ["xray", "ct", "mri", "ultrasound", "pathology"];

export default function ImagingPage() {
  const [imagePath, setImagePath] = useState("");
  const [modality, setModality] = useState("xray");
  const [target, setTarget] = useState("");

  const [describeText, setDescribeText] = useState("");
  const [describeModel, setDescribeModel] = useState<string | null>(null);
  const [describeError, setDescribeError] = useState<string | null>(null);
  const [describing, setDescribing] = useState(false);

  const analyze = useMutation({
    mutationFn: () => api.analyzeImage({ image_path: imagePath, modality, target }),
  });

  const runDescribe = async () => {
    if (!imagePath || describing) return;
    setDescribing(true);
    setDescribeError(null);
    setDescribeText("");
    setDescribeModel(null);

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
            setDescribeText((prev) => prev + event.text);
          } else if (event.event === "final") {
            setDescribeModel(event.model ?? null);
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
            <label className="mb-1 block text-sm font-semibold">Modality</label>
            <select
              value={modality}
              onChange={(e) => setModality(e.target.value)}
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
            <ImageDropzone onUploaded={setImagePath} />
          </div>
        </div>

        <div className="space-y-4">
          {!hasResult && !describing && (
            <div className="card flex h-full min-h-[220px] items-center justify-center text-center text-sm text-muted">
              Run an analysis or vision description to see AI findings here
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
                  Generated by {describeModel} — requires professional review, not a diagnosis.
                </p>
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
