"use client";

import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarDays,
  FileUp,
  FlaskConical,
  Image as ImageIcon,
  NotebookPen,
  Pill,
  Stethoscope,
} from "lucide-react";
import { api } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import StatusPill from "@/components/status-pill";
import AgentBadge from "@/components/agent-badge";

function AddNoteCard({ patientId }: { patientId: string }) {
  const [content, setContent] = useState("");
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const onIngested = () => {
    queryClient.invalidateQueries({ queryKey: ["patient", patientId] });
  };

  const addNote = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/patients/${patientId}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json() as Promise<{ events_added: unknown[] }>;
    },
    onSuccess: () => {
      setContent("");
      onIngested();
    },
  });

  const uploadPdf = useMutation({
    mutationFn: (file: File) => api.uploadNote(patientId, file),
    onSuccess: onIngested,
    onSettled: () => {
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
  });

  const busy = addNote.isPending || uploadPdf.isPending;
  const status = busy
    ? "Extracting events with the local model…"
    : uploadPdf.isSuccess
      ? `${uploadPdf.data.events_added.length} event(s) extracted from ${uploadPdf.data.source_file}`
      : addNote.isSuccess
        ? `${addNote.data.events_added.length} event(s) added to the timeline`
        : uploadPdf.isError
          ? (uploadPdf.error as Error)?.message?.includes("422")
            ? "No text found — scanned PDFs (OCR) are not supported yet."
            : "Upload failed — are you signed in?"
          : addNote.isError
            ? "Failed — are you signed in?"
            : "";

  return (
    <div className="card">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-bold">
          <NotebookPen size={16} className="text-primary" /> Add clinical note
        </h2>
        <AgentBadge name="auto-timeline" />
      </div>
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={3}
        placeholder="Paste or write a clinical note — diagnoses, med changes, labs and events are extracted onto the timeline automatically…"
        className="w-full resize-y rounded-xl border border-line/70 p-3 text-sm outline-none focus:border-primary"
      />
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-xs text-muted">{status}</span>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) uploadPdf.mutate(file);
          }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
          aria-label="Upload a clinical note as PDF"
          className="flex items-center gap-1.5 rounded-xl border border-line/70 px-3 py-2 text-sm font-semibold text-ink/80 hover:bg-surface disabled:opacity-40"
        >
          <FileUp size={14} />
          {uploadPdf.isPending ? "Reading PDF…" : "Upload PDF"}
        </button>
        <button
          onClick={() => addNote.mutate()}
          disabled={content.trim().length < 10 || busy}
          className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {addNote.isPending ? "Analyzing…" : "Save & extract"}
        </button>
      </div>
    </div>
  );
}

const eventIcons: Record<string, typeof Pill> = {
  diagnosis: Stethoscope,
  medication: Pill,
  lab: FlaskConical,
  imaging: ImageIcon,
  event: CalendarDays,
};

export default function PatientProfilePage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { data: patient, isLoading } = useQuery({
    queryKey: ["patient", id],
    queryFn: () => api.patient(id),
  });

  if (isLoading) return <div className="text-muted">Loading patient…</div>;
  if (!patient) return <div className="card text-danger">Patient not found.</div>;

  return (
    <div className="space-y-5">
      <div className="card flex flex-wrap items-center gap-5">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-soft text-lg font-bold text-primary">
          {patient.name.split(" ").map((n) => n[0]).join("")}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-extrabold">{patient.name}</h1>
          <p className="text-sm text-muted">
            {patient.medical_record_number} · {patient.age}y · {patient.sex}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {patient.risk_level && <StatusPill label={`${patient.risk_level} risk`} />}
          <StatusPill label={patient.status} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <AddNoteCard patientId={patient.id} />

          {/* Intelligent Timeline — the differentiating feature */}
          <div className="card">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-bold">Intelligent Timeline</h2>
              <AgentBadge name="AI-organized" />
            </div>
            <ol className="relative ml-3 space-y-5 border-l-2 border-line/60 pl-6">
              {patient.timeline.map((event, i) => {
                const Icon = eventIcons[event.type] ?? CalendarDays;
                return (
                  <li key={i} className="relative">
                    <span className="absolute -left-[31px] flex h-5 w-5 items-center justify-center rounded-full bg-primary-soft">
                      <Icon size={11} className="text-primary" />
                    </span>
                    <div className="text-xs text-muted">{event.date}</div>
                    <div className="flex items-center gap-2 font-semibold">
                      {event.title}
                      {event.ai_generated && <AgentBadge name="AI-extracted" />}
                    </div>
                    {event.detail && <div className="text-sm text-muted">{event.detail}</div>}
                  </li>
                );
              })}
            </ol>
          </div>
        </div>

        <div className="space-y-4">
          {patient.risk_flags && patient.risk_flags.length > 0 && (
            <div className="card">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-bold">Risk Flags</h2>
                <StatusPill label={patient.risk_level ?? "low"} />
              </div>
              <ul className="space-y-2.5">
                {patient.risk_flags.map((flag, i) => (
                  <li
                    key={i}
                    title={flag.detail}
                    className="flex items-start gap-2 rounded-lg p-1.5 text-sm transition-colors hover:bg-surface"
                  >
                    <span className="relative mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center">
                      {flag.severity === "high" && (
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-danger/40" />
                      )}
                      <AlertTriangle
                        size={15}
                        aria-hidden
                        className={`relative ${flag.severity === "high" ? "text-danger" : "text-warning"}`}
                      />
                    </span>
                    <div>
                      <div className="font-semibold">{flag.label}</div>
                      <div className="text-xs text-muted">{flag.detail}</div>
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-muted">
                Rule-based screening — verify clinically.
              </p>
            </div>
          )}

          <div className="card">
            <h2 className="mb-3 font-bold">Lab Results</h2>
            <ul className="space-y-2 text-sm">
              {Object.entries(patient.lab_results).map(([key, value]) => (
                <li key={key} className="flex justify-between">
                  <span className="uppercase text-muted">{key}</span>
                  <span className="font-semibold">{value}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h2 className="mb-3 font-bold">Medications</h2>
            <div className="flex flex-wrap gap-1.5">
              {patient.medications.map((med) => (
                <span key={med} className="rounded-full bg-surface px-2.5 py-1 text-xs font-medium">
                  {med}
                </span>
              ))}
            </div>
          </div>

          <div className="card">
            <h2 className="mb-3 font-bold">Allergies</h2>
            {patient.allergies.length ? (
              <div className="flex flex-wrap gap-1.5">
                {patient.allergies.map((allergy) => (
                  <span key={allergy} className="rounded-full bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger">
                    {allergy}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">None recorded</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
