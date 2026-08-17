"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Eye, ScanEye } from "lucide-react";
import { api } from "@/lib/api";
import AgentBadge from "@/components/agent-badge";
import ImageDropzone from "@/components/image-dropzone";

const modalities = ["xray", "ct", "mri", "ultrasound", "pathology"];

export default function ImagingPage() {
  const [imagePath, setImagePath] = useState("");
  const [modality, setModality] = useState("xray");
  const [target, setTarget] = useState("");

  const analyze = useMutation({
    mutationFn: () => api.analyzeImage({ image_path: imagePath, modality, target }),
  });

  const describe = useMutation({
    mutationFn: () => api.describeImage({ image_path: imagePath, clinical_focus: target }),
  });

  const hasResult = describe.data || analyze.data;

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
            onClick={() => describe.mutate()}
            disabled={!imagePath || describe.isPending}
            className="ai-badge flex items-center gap-2 rounded-xl !px-4 !py-2.5 !text-sm font-semibold disabled:opacity-40"
            aria-label="Describe image with the local vision model"
          >
            <Eye size={16} />
            {describe.isPending ? "Describing…" : "Describe with Vision AI"}
          </button>
        </div>
      </div>

      {/* Side-by-side: original image on the left, AI findings on the right */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card flex items-center justify-center !p-3">
          <ImageDropzone onUploaded={setImagePath} />
        </div>

        <div className="space-y-4">
          {!hasResult && (
            <div className="card flex h-full min-h-[220px] items-center justify-center text-center text-sm text-muted">
              Run an analysis or vision description to see AI findings here
            </div>
          )}

          {describe.data && (
            <div
              className="card border-2"
              style={{ borderImage: "linear-gradient(135deg,#8C92AC,#D1D5DB) 1" }}
            >
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-bold">Vision description</h2>
                <AgentBadge name="vision-ai" />
              </div>
              {describe.data.description ? (
                <p className="whitespace-pre-wrap text-sm leading-relaxed">
                  {describe.data.description}
                </p>
              ) : (
                <p className="text-sm text-danger">
                  {describe.data.message ?? describe.data.error ?? "No description returned."}
                </p>
              )}
              <p className="mt-3 text-xs text-muted">
                Generated locally by {describe.data.model ?? "the vision model"} — requires
                professional review, not a diagnosis.
              </p>
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
