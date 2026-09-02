"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarDays,
  FileUp,
  FlaskConical,
  Image as ImageIcon,
  NotebookPen,
  Pill,
  Share2,
  Stethoscope,
  UserPlus,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { parseInteractionLabel } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";
import AgentBadge from "@/components/agent-badge";
import ShareResultSheet from "@/components/results/share-result-sheet";
import InteractionCheckerCard from "@/components/patients/interaction-checker-card";
import FollowupCard from "@/components/patients/followup-card";
import { useToast } from "@/components/ui/toast";

function MedicationsCard({ patientId, medications }: { patientId: string; medications: string[] }) {
  const { t } = useLanguage();
  const [name, setName] = useState("");
  const [dosage, setDosage] = useState("");
  const queryClient = useQueryClient();
  const showToast = useToast();

  const addMedication = useMutation({
    mutationFn: () => api.addMedication(patientId, { name, dosage }),
    onSuccess: () => {
      setName("");
      setDosage("");
      queryClient.invalidateQueries({ queryKey: ["patient", patientId] });
      showToast(t("patientDetail.medications.prescribed"));
    },
    onError: () => showToast(t("patientDetail.medications.error.prescribe"), "error"),
  });

  return (
    <div className="card">
      <h2 className="mb-3 font-bold">{t("patientDetail.medications.title")}</h2>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {medications.length === 0 && (
          <p className="text-sm text-muted">{t("patientDetail.medications.none")}</p>
        )}
        {medications.map((med) => (
          <span key={med} className="rounded-full bg-surface px-2.5 py-1 text-xs font-medium">
            {med}
          </span>
        ))}
      </div>
      <div className="flex gap-2 border-t border-line/60 pt-3">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("patientDetail.medications.namePlaceholder")}
          className="input flex-1 rounded-lg py-2"
        />
        <input
          value={dosage}
          onChange={(e) => setDosage(e.target.value)}
          placeholder={t("patientDetail.medications.dosagePlaceholder")}
          className="input w-32 rounded-lg py-2"
        />
        <button
          onClick={() => addMedication.mutate()}
          disabled={!name.trim() || addMedication.isPending}
          className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-semibold text-white disabled:opacity-40"
        >
          <Pill size={13} />
          {addMedication.isPending
            ? t("patientDetail.medications.prescribing")
            : t("patientDetail.medications.prescribe")}
        </button>
      </div>
    </div>
  );
}

// How long to keep checking for background-extracted events before giving
// up and assuming the note simply had none to extract. 6s x 30 = 180s — a
// single local-model run has taken up to ~90s; this leaves headroom for a
// second note queueing behind it on the same (single-threaded) local model.
const POLL_INTERVAL_MS = 6000;
const POLL_MAX_ATTEMPTS = 30;

function AddNoteCard({ patientId }: { patientId: string }) {
  const { t } = useLanguage();
  const [content, setContent] = useState("");
  const [pollState, setPollState] = useState<"idle" | "polling" | "found" | "none">("idle");
  const [foundCount, setFoundCount] = useState(0);
  const [sourceFile, setSourceFile] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  const onIngested = () => {
    queryClient.invalidateQueries({ queryKey: ["patient", patientId] });
  };

  /** The note itself saves in well under a second (see `_ingest_note` on the
   * backend); the LLM timeline-event extraction that used to block this
   * response now runs afterward in the background, so there's nothing to
   * await here — just poll the patient record for new timeline rows until
   * one shows up or we give up. */
  const pollForEvents = (baseline: number, attemptsLeft: number) => {
    pollTimer.current = setTimeout(async () => {
      const fresh = await queryClient.fetchQuery({
        queryKey: ["patient", patientId],
        queryFn: () => api.patient(patientId),
      });
      const delta = fresh.timeline.length - baseline;
      if (delta > 0) {
        setFoundCount(delta);
        setPollState("found");
        return;
      }
      if (attemptsLeft <= 1) {
        setPollState("none");
        return;
      }
      pollForEvents(baseline, attemptsLeft - 1);
    }, POLL_INTERVAL_MS);
  };

  const startPolling = () => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
    const baseline =
      queryClient.getQueryData<{ timeline: unknown[] }>(["patient", patientId])?.timeline?.length ?? 0;
    setPollState("polling");
    pollForEvents(baseline, POLL_MAX_ATTEMPTS);
  };

  const addNote = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/patients/${patientId}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      return res.json() as Promise<{ events_added: unknown[]; processing?: boolean }>;
    },
    onSuccess: () => {
      setContent("");
      setSourceFile(null);
      onIngested();
      startPolling();
    },
  });

  const uploadPdf = useMutation({
    mutationFn: (file: File) => api.uploadNote(patientId, file),
    onSuccess: (data) => {
      setSourceFile(data.source_file);
      onIngested();
      startPolling();
    },
    onSettled: () => {
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
  });

  const busy = addNote.isPending || uploadPdf.isPending;
  const status = busy
    ? t("patientDetail.notes.extracting")
    : pollState === "polling"
      ? t("patientDetail.notes.processingBackground")
      : pollState === "found"
        ? sourceFile
          ? t("patientDetail.notes.eventsExtractedFrom")
              .replace("{count}", String(foundCount))
              .replace("{file}", sourceFile)
          : t("patientDetail.notes.eventsAdded").replace("{count}", String(foundCount))
        : pollState === "none"
          ? t("patientDetail.notes.noEventsFound")
          : uploadPdf.isError
            ? (uploadPdf.error as Error)?.message?.includes("422")
              ? t("patientDetail.notes.error.ocrUnsupported")
              : t("patientDetail.notes.error.uploadFailed")
            : addNote.isError
              ? t("patientDetail.notes.error.addFailed")
              : "";

  return (
    <div className="card">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-bold">
          <NotebookPen size={16} className="text-primary" /> {t("patientDetail.notes.title")}
        </h2>
        <AgentBadge name={t("patientDetail.notes.autoTimeline")} />
      </div>
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={4}
        placeholder={t("patientDetail.notes.placeholder")}
        className="input resize-y rounded-xl p-3"
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
          aria-label={t("patientDetail.notes.uploadAria")}
          className="flex items-center gap-1.5 rounded-xl border border-line/70 px-3 py-2 text-sm font-semibold text-ink/80 hover:bg-surface disabled:opacity-40"
        >
          <FileUp size={14} />
          {uploadPdf.isPending ? t("patientDetail.notes.readingPdf") : t("patientDetail.notes.uploadPdf")}
        </button>
        <button
          onClick={() => addNote.mutate()}
          disabled={content.trim().length < 10 || busy}
          className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
        >
          {addNote.isPending ? t("patientDetail.notes.analyzing") : t("patientDetail.notes.saveExtract")}
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
  const { t } = useLanguage();
  const showToast = useToast();
  const [shareOpen, setShareOpen] = useState(false);
  const { data: patient, isLoading } = useQuery({
    queryKey: ["patient", id],
    queryFn: () => api.patient(id),
  });

  const invitePatient = useMutation({
    mutationFn: () => api.createInvite(id),
    onSuccess: (invite) => {
      // A raw "{invite_id}.{secret}" string is meaningless to a patient
      // asked to paste it in — hand them a plain link instead, with the
      // code embedded as a query param that /portal/claim reads silently.
      const link = `${window.location.origin}/portal/claim?code=${encodeURIComponent(invite.code)}`;
      navigator.clipboard?.writeText(link).catch(() => {});
      showToast(t("patientDetail.inviteCopied"));
    },
    onError: (err) => {
      showToast(err instanceof ApiError ? err.message : t("patientDetail.error.invite"), "error");
    },
  });

  if (isLoading) return <div className="text-muted">{t("patientDetail.loading")}</div>;
  if (!patient) return <div className="card text-danger">{t("patientDetail.notFound")}</div>;

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
          <button
            onClick={() => invitePatient.mutate()}
            disabled={invitePatient.isPending}
            className="btn-secondary"
            title={t("patientDetail.inviteTooltip")}
          >
            <UserPlus size={15} /> {t("patientDetail.invitePortal")}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <AddNoteCard patientId={patient.id} />
          <FollowupCard patientId={patient.id} />

          {/* Intelligent Timeline — the differentiating feature */}
          <div className="card">
            <div className="mb-1 flex items-center justify-between">
              <h2 className="font-bold">{t("patientDetail.timeline.title")}</h2>
              <div className="flex items-center gap-2">
                <button onClick={() => setShareOpen(true)} className="btn-secondary py-1.5 text-xs">
                  <Share2 size={13} /> {t("patientDetail.timeline.share")}
                </button>
                <AgentBadge name={t("patientDetail.timeline.aiOrganized")} />
              </div>
            </div>
            <p className="mb-4 text-xs text-muted">{t("patientDetail.timeline.subtitle")}</p>
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
                      {event.ai_generated && (
                        <AgentBadge name={t("patientDetail.timeline.aiExtracted")} />
                      )}
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
                <h2 className="font-bold">{t("patientDetail.riskFlags.title")}</h2>
                <StatusPill label={patient.risk_level ?? "low"} />
              </div>
              <ul className="space-y-2.5">
                {patient.risk_flags.map((flag, i) => {
                  // A drug-interaction flag's label is the formal
                  // "Interaction: X + Y" audit-log form — shown here as
                  // just "X + Y" since the surrounding card already says
                  // this is a risk flag.
                  const interaction = parseInteractionLabel(flag.label);
                  const label = interaction ? `${interaction.drugA} + ${interaction.drugB}` : flag.label;
                  return (
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
                        <div className="font-semibold">{label}</div>
                        <div className="text-xs text-muted">{flag.detail}</div>
                      </div>
                    </li>
                  );
                })}
              </ul>
              <p className="mt-3 text-xs text-muted">{t("patientDetail.riskFlags.disclaimer")}</p>
            </div>
          )}

          <InteractionCheckerCard medications={patient.medications} />

          <div className="card">
            <h2 className="mb-1 font-bold">{t("patientDetail.labResults.title")}</h2>
            <p className="mb-3 text-xs text-muted">{t("patientDetail.labResults.subtitle")}</p>
            <ul className="space-y-2 text-sm">
              {Object.entries(patient.lab_results).map(([key, value]) => (
                <li key={key} className="flex justify-between gap-3">
                  <span className="text-muted">
                    {t(`patientDetail.labResults.key.${key}`) === `patientDetail.labResults.key.${key}`
                      ? key.toUpperCase()
                      : t(`patientDetail.labResults.key.${key}`)}
                  </span>
                  <span className="font-semibold">{value}</span>
                </li>
              ))}
            </ul>
          </div>

          <MedicationsCard patientId={patient.id} medications={patient.medications} />

          <div className="card">
            <h2 className="mb-3 font-bold">{t("patientDetail.allergies.title")}</h2>
            {patient.allergies.length ? (
              <div className="flex flex-wrap gap-1.5">
                {patient.allergies.map((allergy) => (
                  <span key={allergy} className="rounded-full bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger">
                    {allergy}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">{t("patientDetail.allergies.none")}</p>
            )}
          </div>
        </div>
      </div>

      <ShareResultSheet open={shareOpen} onClose={() => setShareOpen(false)} patientId={patient.id} />
    </div>
  );
}
