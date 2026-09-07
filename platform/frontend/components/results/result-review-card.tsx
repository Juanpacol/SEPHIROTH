"use client";

/** One result, and where it is in the loop.
 *
 * The Close button is disabled — with the reason written next to it — when the
 * clinician decided the patient needs telling and they have not been told. The
 * server refuses that transition regardless; showing it here means the refusal
 * is never a surprise 409 arriving after someone thought they were done.
 *
 * The classification's reason is always on screen. A severity a clinician
 * cannot trace back to a threshold is one they have to take on faith, and this
 * one is arithmetic they can check in a second.
 */

import { useState } from "react";
import { AlertTriangle, Check, Lock, MessageSquare } from "lucide-react";

import { type Disposition, type ResultReview } from "@/lib/api";
import { useLanguage } from "@/lib/language";

const DISPOSITIONS: Disposition[] = [
  "normal",
  "abnormal_expected",
  "action_taken",
  "needs_patient_contact",
];

const SEVERITY_TONE: Record<ResultReview["severity"], string> = {
  critical: "bg-danger text-white",
  abnormal: "bg-warning/20 text-ink",
  unclassified: "bg-surface text-ink/70",
  normal: "bg-surface text-ink/60",
};

interface Props {
  review: ResultReview;
  busy?: boolean;
  onReview: (body: { disposition: Disposition; note: string }) => void;
  onCommunicate: () => void;
  onClose: () => void;
  onReopen: () => void;
}

function resultLine(review: ResultReview): string {
  const result = review.result;
  if (result.missing) return "—";
  if (result.kind === "lab") {
    const range =
      result.reference_low != null && result.reference_high != null
        ? ` (${result.reference_low}–${result.reference_high})`
        : "";
    return `${result.test_name}: ${result.value} ${result.unit ?? ""}${range}`.trim();
  }
  return `${result.modality} ${result.body_part}${result.finding_summary ? ` — ${result.finding_summary}` : ""}`;
}

export default function ResultReviewCard({
  review,
  busy,
  onReview,
  onCommunicate,
  onClose,
  onReopen,
}: Props) {
  const { t } = useLanguage();
  const [disposition, setDisposition] = useState<Disposition>(
    review.disposition ?? (review.severity === "normal" ? "normal" : "action_taken"),
  );
  const [note, setNote] = useState(review.note);

  const open = review.status !== "closed";
  // The one guard that makes the states mean anything.
  const noteRequired = disposition !== "normal";
  const canSubmitReview = !noteRequired || note.trim().length > 0;

  return (
    <article className="card flex flex-col gap-3">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs text-ink/50">{review.patient_name ?? review.patient_id}</p>
          <p className="text-sm font-medium">{resultLine(review)}</p>
          <p className="text-xs text-ink/60">{review.classification_reason}</p>
        </div>
        <span
          className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${SEVERITY_TONE[review.severity]}`}
        >
          {t(`results.severity.${review.severity}`)}
        </span>
      </header>

      <ol className="flex flex-wrap items-center gap-1.5 text-xs text-ink/50">
        {(["received", "reviewed", "communicated", "closed"] as const).map((step, index) => {
          const reached =
            ["received", "reviewed", "communicated", "closed"].indexOf(review.status) >= index;
          return (
            <li key={step} className={reached ? "font-medium text-ink" : ""}>
              {index > 0 ? <span className="mr-1.5 text-ink/30">→</span> : null}
              {t(`results.step.${step}`)}
            </li>
          );
        })}
      </ol>

      {review.status === "received" ? (
        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-ink/70">{t("results.decision")}</span>
            <select
              value={disposition}
              onChange={(event) => setDisposition(event.target.value as Disposition)}
              className="tap rounded-lg border border-border bg-white px-3 py-2 text-sm"
            >
              {DISPOSITIONS.map((option) => (
                <option key={option} value={option}>
                  {t(`results.disposition.${option}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-ink/70">
              {noteRequired ? t("results.noteRequired") : t("results.noteOptional")}
            </span>
            <textarea
              rows={2}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm"
            />
          </label>
          <button
            type="button"
            onClick={() => onReview({ disposition, note })}
            disabled={busy || !canSubmitReview}
            className="btn-primary tap self-start disabled:opacity-50"
          >
            {t("results.recordDecision")}
          </button>
        </div>
      ) : (
        <div className="border-t border-border pt-3 text-sm">
          <p>
            <span className="text-ink/60">{t("results.decision")}: </span>
            {review.disposition ? t(`results.disposition.${review.disposition}`) : "—"}
          </p>
          {review.note ? <p className="text-ink/80">{review.note}</p> : null}
        </div>
      )}

      {review.needs_communication ? (
        <p className="flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-xs">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden />
          <span>{t("results.mustCommunicate")}</span>
        </p>
      ) : null}

      <footer className="flex flex-wrap gap-2">
        {review.needs_communication ? (
          <button
            type="button"
            onClick={onCommunicate}
            disabled={busy}
            className="btn-secondary tap"
          >
            <MessageSquare className="mr-1.5 inline h-3.5 w-3.5" aria-hidden />
            {t("results.communicate")}
          </button>
        ) : null}

        {open && review.status !== "received" ? (
          <button
            type="button"
            onClick={onClose}
            disabled={busy || !review.closable}
            title={review.closable ? undefined : t("results.mustCommunicate")}
            className="btn-primary tap disabled:opacity-50"
          >
            <Check className="mr-1.5 inline h-3.5 w-3.5" aria-hidden />
            {t("results.close")}
          </button>
        ) : null}

        {review.status === "closed" ? (
          <>
            <span className="flex items-center gap-1.5 rounded-full bg-surface px-3 py-1 text-xs">
              <Lock className="h-3.5 w-3.5" aria-hidden />
              {t("results.step.closed")}
            </span>
            <button type="button" onClick={onReopen} disabled={busy} className="btn-secondary tap">
              {t("results.reopen")}
            </button>
          </>
        ) : null}
      </footer>
    </article>
  );
}
