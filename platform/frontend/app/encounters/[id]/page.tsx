"use client";

/** One visit, being written.
 *
 * Three states, and the page is honest about which one it is in: a draft that
 * can be edited, a signed record that cannot, and an amendment that can again
 * but says on its face that it is a correction.
 *
 * Saving is explicit rather than on every keystroke. A note is not a chat box:
 * an autosave that fires mid-sentence puts half-written clinical text in a
 * record, and an autosave that fails silently loses the other half.
 */

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Lock } from "lucide-react";

import { api, type Encounter, type NoteDraft, type OrderKind } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import Dialog from "@/components/ui/dialog";
import NoteDraftPanel from "@/components/encounters/note-draft-panel";
import OrdersEditor from "@/components/encounters/orders-editor";
import VitalsForm from "@/components/encounters/vitals-form";

const SECTIONS = ["subjective", "objective", "assessment", "plan"] as const;
type Section = (typeof SECTIONS)[number];

type Narrative = Record<Section | "chief_complaint" | "patient_instructions", string>;

function narrativeOf(encounter: Encounter): Narrative {
  return {
    chief_complaint: encounter.chief_complaint,
    subjective: encounter.subjective,
    objective: encounter.objective,
    assessment: encounter.assessment,
    plan: encounter.plan,
    patient_instructions: encounter.patient_instructions,
  };
}

export default function EncounterPage() {
  const { t } = useLanguage();
  const params = useParams<{ id: string }>();
  const id = params.id;
  const queryClient = useQueryClient();

  const [draft, setDraft] = useState<Narrative | null>(null);
  const [noteSource, setNoteSource] = useState<Encounter["note_source"] | null>(null);
  const [noteModel, setNoteModel] = useState<string | null>(null);
  const [amending, setAmending] = useState(false);
  const [amendReason, setAmendReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const encounterQuery = useQuery({
    queryKey: ["encounter", id],
    queryFn: () => api.encounter(id),
  });
  const encounter = encounterQuery.data;

  const specsQuery = useQuery({ queryKey: ["vitals-spec"], queryFn: api.vitalsSpec });
  // Pre-visit brief (SPEC-023's companion panel) reads open Tasks — deferred
  // to the task-inbox restoration phase along with `api.preVisitBrief`.

  // The server's copy wins whenever it changes underneath — after a save, a
  // sign, or an amendment — except while the clinician has unsaved edits.
  useEffect(() => {
    if (encounter && draft === null) setDraft(narrativeOf(encounter));
  }, [encounter, draft]);

  const dirty = useMemo(() => {
    if (!encounter || !draft) return false;
    const saved = narrativeOf(encounter);
    return SECTIONS.concat(["chief_complaint", "patient_instructions"] as never).some(
      (field) => saved[field as keyof Narrative] !== draft[field as keyof Narrative],
    );
  }, [encounter, draft]);

  const save = useMutation({
    mutationFn: (body: Partial<Encounter>) => api.updateEncounter(id, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(["encounter", id], updated);
      setDraft(narrativeOf(updated));
      setNoteSource(null);
      setNoteModel(null);
      setError(null);
    },
    onError: (err: Error) => setError(err.message),
  });

  const sign = useMutation({
    mutationFn: () => api.signEncounter(id),
    onSuccess: (updated) => {
      queryClient.setQueryData(["encounter", id], updated);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["badges"] });
      setDraft(narrativeOf(updated));
    },
    onError: (err: Error) => setError(err.message),
  });

  const amend = useMutation({
    mutationFn: (reason: string) => api.amendEncounter(id, reason),
    onSuccess: (updated) => {
      queryClient.setQueryData(["encounter", id], updated);
      setDraft(narrativeOf(updated));
      setAmending(false);
      setAmendReason("");
    },
    onError: (err: Error) => setError(err.message),
  });

  const addOrder = useMutation({
    mutationFn: (order: { kind: OrderKind; detail: string; due_in_days: number | null }) =>
      api.addEncounterOrder(id, order),
    onSuccess: (updated) => queryClient.setQueryData(["encounter", id], updated),
    onError: (err: Error) => setError(err.message),
  });

  const removeOrder = useMutation({
    mutationFn: (orderId: string) => api.removeEncounterOrder(id, orderId),
    onSuccess: () => encounterQuery.refetch(),
    onError: (err: Error) => setError(err.message),
  });

  if (encounterQuery.isLoading || !encounter || !draft) {
    return <div className="h-40 animate-pulse rounded-xl bg-surface" aria-busy="true" />;
  }

  const editable = encounter.editable;

  function applyDraft(drafted: NoteDraft) {
    setDraft((current) =>
      current
        ? {
            ...current,
            subjective: drafted.subjective || current.subjective,
            objective: drafted.objective || current.objective,
            assessment: drafted.assessment || current.assessment,
            plan: drafted.plan || current.plan,
          }
        : current,
    );
    // Recorded only if this draft is what actually gets saved, so a clinician
    // who applies a suggestion and then rewrites it is not attributed to a
    // model (B-11).
    setNoteSource(drafted.source === "llm" ? "llm" : "template");
    setNoteModel(drafted.model);
  }

  function saveNarrative() {
    save.mutate({
      ...draft,
      ...(noteSource ? { note_source: noteSource, note_model: noteModel } : {}),
    } as Partial<Encounter>);
  }

  return (
    <div className="flex flex-col gap-4 pb-24 md:pb-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs text-ink/50">
            <Link href={`/patients/${encounter.patient_id}`} className="hover:underline">
              {encounter.patient_name ?? encounter.patient_id}
            </Link>
            {" · "}
            {new Date(encounter.started_at).toLocaleString()}
          </p>
          <h1 className="text-xl font-semibold">
            {encounter.chief_complaint || t("encounter.untitled")}
          </h1>
        </div>

        <div className="flex items-center gap-2">
          {encounter.status !== "draft" ? (
            <span className="flex items-center gap-1.5 rounded-full bg-surface px-3 py-1 text-xs">
              <Lock className="h-3.5 w-3.5" aria-hidden />
              {t(`encounter.status.${encounter.status}`)}
            </span>
          ) : null}
          {encounter.note_source === "llm" ? (
            <span className="rounded-full bg-gradient-to-r from-sephiroth-start to-sephiroth-end px-3 py-1 text-xs text-white">
              {t("encounter.aiDrafted")}
            </span>
          ) : null}
        </div>
      </header>

      {encounter.amendment_reason ? (
        <p className="rounded-lg bg-warning/10 px-3 py-2 text-sm">
          <span className="font-medium">{t("encounter.amendedNotice")}: </span>
          {encounter.amendment_reason}
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="rounded-lg bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      <section className="card flex flex-col gap-3">
        <h2 className="text-sm font-semibold">{t("encounter.vitals.title")}</h2>
        <VitalsForm
          vitals={encounter.vitals}
          specs={specsQuery.data?.vitals ?? []}
          findings={encounter.vital_findings}
          disabled={!editable || save.isPending}
          onChange={(changed) => {
            const merged: Record<string, number> = { ...encounter.vitals };
            for (const [key, value] of Object.entries(changed)) {
              if (value === "") delete merged[key];
              else merged[key] = value as number;
            }
            save.mutate({ vitals: merged } as Partial<Encounter>);
          }}
        />
      </section>

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <section className="card flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-ink/70">{t("encounter.chiefComplaint")}</span>
            <input
              type="text"
              value={draft.chief_complaint}
              disabled={!editable}
              onChange={(event) =>
                setDraft({ ...draft, chief_complaint: event.target.value })
              }
              className="tap rounded-lg border border-border bg-white px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>

          {SECTIONS.map((section) => (
            <label key={section} className="flex flex-col gap-1">
              <span className="text-xs font-medium text-ink/70">
                {t(`encounter.section.${section}`)}
              </span>
              <textarea
                rows={4}
                value={draft[section]}
                disabled={!editable}
                placeholder={encounter.template[section]}
                onChange={(event) => setDraft({ ...draft, [section]: event.target.value })}
                className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm disabled:opacity-60"
              />
            </label>
          ))}

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-ink/70">
              {t("encounter.patientInstructions")}
            </span>
            <textarea
              rows={3}
              value={draft.patient_instructions}
              disabled={!editable}
              onChange={(event) =>
                setDraft({ ...draft, patient_instructions: event.target.value })
              }
              className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>

          {editable ? (
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={saveNarrative}
                disabled={!dirty || save.isPending}
                className="btn-secondary tap disabled:opacity-50"
              >
                {save.isPending ? t("encounter.saving") : t("encounter.save")}
              </button>
              {dirty ? (
                <span className="text-xs text-ink/50">{t("encounter.unsaved")}</span>
              ) : null}
            </div>
          ) : null}
        </section>

        <div className="flex flex-col gap-4">
          {editable ? (
            <NoteDraftPanel
              encounterId={id}
              specialty={encounter.specialty}
              disabled={save.isPending}
              onApply={applyDraft}
            />
          ) : null}

          <OrdersEditor
            orders={encounter.orders}
            disabled={!editable}
            onAdd={(order) => addOrder.mutate(order)}
            onRemove={(orderId) => removeOrder.mutate(orderId)}
          />
        </div>
      </div>

      <div className="safe-bottom fixed inset-x-0 bottom-16 z-30 border-t border-border bg-white/95 px-4 py-3 backdrop-blur md:static md:border-0 md:bg-transparent md:p-0">
        {editable ? (
          <button
            type="button"
            onClick={() => sign.mutate()}
            disabled={!encounter.signable || dirty || sign.isPending}
            className="btn-primary tap w-full md:w-auto disabled:opacity-50"
          >
            <CheckCircle2 className="mr-1.5 inline h-4 w-4" aria-hidden />
            {sign.isPending ? t("encounter.signing") : t("encounter.sign")}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setAmending(true)}
            className="btn-secondary tap w-full md:w-auto"
          >
            {t("encounter.amend")}
          </button>
        )}
        {editable && dirty ? (
          <p className="mt-1 text-xs text-ink/60">{t("encounter.saveBeforeSigning")}</p>
        ) : null}
      </div>

      <Dialog open={amending} onClose={() => setAmending(false)} title={t("encounter.amend")}>
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink/70">{t("encounter.amendHelp")}</p>
          <textarea
            rows={3}
            value={amendReason}
            onChange={(event) => setAmendReason(event.target.value)}
            className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm"
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setAmending(false)} className="btn-secondary tap">
              {t("common.cancel")}
            </button>
            <button
              type="button"
              onClick={() => amend.mutate(amendReason)}
              disabled={!amendReason.trim() || amend.isPending}
              className="btn-primary tap disabled:opacity-50"
            >
              {t("encounter.amendConfirm")}
            </button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
