"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ClipboardCheck,
  FileUp,
  NotebookPen,
  Pill,
  Share2,
  Stethoscope,
  UserPlus,
} from "lucide-react";
import { api, ApiError, type TimelineEvent } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { parseInteractionLabel, riskLabel } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import StatusPill from "@/components/status-pill";
import AgentBadge from "@/components/agent-badge";
import Sheet from "@/components/ui/sheet";
import VitalsCard from "@/components/patients/vitals-card";
import { initialsOf } from "@/lib/initials";
import AccentTitle from "@/components/landing/accent-title";
import ShareResultSheet from "@/components/results/share-result-sheet";
import InteractionCheckerCard from "@/components/patients/interaction-checker-card";
import FollowupCard from "@/components/patients/followup-card";
import LabsCard from "@/components/patients/labs-card";
import TimelineEventSheet from "@/components/patients/timeline-event-sheet";
import TimelineList from "@/components/patients/timeline-list";
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
      <h2 className="eyebrow mb-3 flex items-center gap-2 text-muted">
        <Pill size={13} className="text-primary-ink" /> {t("patientDetail.medications.title")}
      </h2>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {medications.length === 0 && (
          <p className="text-sm text-muted">{t("patientDetail.medications.none")}</p>
        )}
        {medications.map((med) => (
          <span key={med} className="rounded-full border border-line/60 px-2.5 py-1 text-xs font-medium">
            {med}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 border-t border-line/60 pt-3">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("patientDetail.medications.namePlaceholder")}
          className="input min-w-0 flex-1 basis-40 rounded-lg py-2"
        />
        <input
          value={dosage}
          onChange={(e) => setDosage(e.target.value)}
          placeholder={t("patientDetail.medications.dosagePlaceholder")}
          className="input min-w-0 basis-28 rounded-lg py-2"
        />
        <button
          onClick={() => addMedication.mutate()}
          disabled={!name.trim() || addMedication.isPending}
          className="btn-secondary tap w-full py-2 text-xs disabled:opacity-40"
        >
          <Pill size={13} />
          {addMedication.isPending
            ? t("patientDetail.medications.prescribing")
            : t("patientDetail.medications.prescribe")}
        </button>
      </div>
      <InteractionCheckerCard medications={medications} embedded />
    </div>
  );
}

// How long to keep checking for background-extracted events before giving
// up and assuming the note simply had none to extract. 6s x 30 = 180s — a
// single local-model run has taken up to ~90s; this leaves headroom for a
// second note queueing behind it on the same (single-threaded) local model.
const POLL_INTERVAL_MS = 6000;
const POLL_MAX_ATTEMPTS = 30;

function AddNoteCard({ patientId, bare = false }: { patientId: string; bare?: boolean }) {
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
            ? uploadPdf.error instanceof ApiError && uploadPdf.error.status === 422
              ? t("patientDetail.notes.error.ocrUnsupported")
              : uploadPdf.error instanceof ApiError && uploadPdf.error.status === 413
                ? t("patientDetail.notes.error.tooLarge")
                : t("patientDetail.notes.error.uploadFailed")
            : addNote.isError
              ? t("patientDetail.notes.error.addFailed")
              : "";

  return (
    <div className={bare ? "" : "card"}>
      <div className="mb-2 flex items-center justify-between">
        {!bare && (
          <h2 className="eyebrow flex items-center gap-2 text-muted">
            <NotebookPen size={13} className="text-primary-ink" /> {t("patientDetail.notes.title")}
          </h2>
        )}
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

export default function PatientProfilePage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { t } = useLanguage();
  const router = useRouter();
  const showToast = useToast();
  const [shareOpen, setShareOpen] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);
  const [followupOpen, setFollowupOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent | null>(null);
  const { data: patient, isLoading } = useQuery({
    queryKey: ["patient", id],
    queryFn: () => api.patient(id),
  });

  // Starting a visit is the primary action on a patient during clinic hours,
  // so it opens the encounter straight away rather than dropping the clinician
  // on a list to find the one they just made.
  const startEncounter = useMutation({
    mutationFn: () => api.startEncounter({ patient_id: id }),
    onSuccess: (encounter) => {
      router.push(`/encounters/${encounter.id}`);
    },
    onError: (err) => {
      showToast(err instanceof ApiError ? err.message : t("encounter.start"), "error");
    },
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
      <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary-soft font-mono text-sm font-semibold tracking-wider text-primary-ink">
            {initialsOf(patient.name)}
          </div>
          <div className="min-w-0">
            <AccentTitle
              as="h1"
              text={patient.name}
              accentWords={1}
              accentClass="text-primary-ink"
              className="text-3xl sm:text-4xl"
            />
            <p className="mt-1 font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
              {patient.medical_record_number} · {patient.age}y · {patient.sex}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {patient.risk_level && <StatusPill label={`${patient.risk_level} risk`} />}
              {patient.allergies.length > 0 && (
                <>
                  <span className="eyebrow text-muted">{t("patientDetail.snapshot.allergies")}</span>
                  {patient.allergies.map((allergy) => (
                    <span
                      key={allergy}
                      className="rounded-full bg-danger/10 px-2.5 py-0.5 text-[11px] font-semibold text-danger"
                    >
                      {allergy}
                    </span>
                  ))}
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          <button
            onClick={() => invitePatient.mutate()}
            disabled={invitePatient.isPending}
            className="nav-underline tap px-3.5 py-2 text-sm font-medium text-muted hover:text-ink"
            title={t("patientDetail.inviteTooltip")}
          >
            <UserPlus size={14} className="mr-1.5 inline" /> {t("patientDetail.invitePortal")}
          </button>
          <button
            onClick={() => startEncounter.mutate()}
            disabled={startEncounter.isPending}
            className="btn-primary tap w-full sm:w-auto"
          >
            <Stethoscope size={15} /> {t("encounter.start")}
          </button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {patient.risk_flags && patient.risk_flags.length > 0 && (
              <div className="card">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="eyebrow flex items-center gap-2 text-muted">
                    <AlertTriangle size={13} className="text-danger" /> {t("patientDetail.riskFlags.title")}
                  </h2>
                  <StatusPill label={patient.risk_level ?? "low"} />
                </div>
                <ul className="space-y-2.5">
                  {patient.risk_flags.map((flag, i) => {
                    const interaction = parseInteractionLabel(flag.label);
                    const label = interaction
                      ? `${interaction.drugA} + ${interaction.drugB}`
                      : riskLabel(flag.label, t);
                    return (
                      <li key={i} title={flag.detail} className="flex items-start gap-2 text-sm">
                        <AlertTriangle
                          size={14}
                          aria-hidden
                          className={`mt-0.5 shrink-0 ${flag.severity === "high" ? "text-danger" : "text-warning"}`}
                        />
                        <div className="min-w-0">
                          <div className="font-semibold">{label}</div>
                          <div className="text-xs text-muted">{flag.detail}</div>
                        </div>
                      </li>
                    );
                  })}
                </ul>
                <p className="mt-3 text-[11px] text-muted">{t("patientDetail.riskFlags.disclaimer")}</p>
              </div>
            )}
            <VitalsCard patientId={patient.id} />
          </div>

          {/* Intelligent Timeline — the differentiating feature */}
          <div className="card">
            <div className="mb-1 flex items-center justify-between gap-2">
              <h2 className="eyebrow text-muted">{t("patientDetail.timeline.title")}</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShareOpen(true)}
                  className="nav-underline tap px-2.5 py-1.5 text-xs font-medium text-muted hover:text-ink"
                >
                  <Share2 size={12} className="mr-1.5 inline" /> {t("patientDetail.timeline.share")}
                </button>
                <AgentBadge name={t("patientDetail.timeline.aiOrganized")} />
              </div>
            </div>
            <p className="mb-4 text-xs text-muted">{t("patientDetail.timeline.subtitle")}</p>
            <TimelineList events={patient.timeline} onSelect={setSelectedEvent} />
          </div>
        </div>

        <div className="space-y-4">
          <div className="card">
            <h2 className="eyebrow mb-2 text-muted">{t("patientDetail.actions.title")}</h2>
            <div className="flex flex-col gap-1">
              <button onClick={() => setNoteOpen(true)} className="btn-ghost tap justify-start">
                <NotebookPen size={15} /> {t("patientDetail.notes.title")}
              </button>
              <button onClick={() => setFollowupOpen(true)} className="btn-ghost tap justify-start">
                <ClipboardCheck size={15} /> {t("patientDetail.followup.title")}
              </button>
            </div>
          </div>

          <LabsCard patientId={patient.id} snapshot={patient.lab_results} />

          <MedicationsCard patientId={patient.id} medications={patient.medications} />
        </div>
      </div>

      <Sheet
        open={noteOpen}
        onClose={() => setNoteOpen(false)}
        side="right"
        title={t("patientDetail.notes.title")}
      >
        <AddNoteCard patientId={patient.id} bare />
      </Sheet>
      <Sheet
        open={followupOpen}
        onClose={() => setFollowupOpen(false)}
        side="right"
        title={t("patientDetail.followup.title")}
      >
        <FollowupCard patientId={patient.id} bare />
      </Sheet>

      <ShareResultSheet open={shareOpen} onClose={() => setShareOpen(false)} patientId={patient.id} />
      <TimelineEventSheet event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </div>
  );
}
