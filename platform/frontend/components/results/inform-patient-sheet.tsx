"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Sheet from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, type ResultReview } from "@/lib/api";
import { friendlyTestName } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";

const MAX_MESSAGE = 2000;

/** Tell the patient about a result, from the inbox.
 *
 * What it sends is the clinician's own words, so the message starts from a
 * suggestion they can rewrite and is never sent blank. The entry the portal
 * renders is made by the server from the result unless one of the patient's own
 * is picked here: a result recorded on its own is not a timeline entry, so
 * there would otherwise be nothing to point at.
 */
export default function InformPatientSheet({
  review,
  onClose,
  onDone,
}: {
  review: ResultReview | null;
  onClose: () => void;
  onDone: (updated: ResultReview) => void;
}) {
  const { t, lang } = useLanguage();
  const showToast = useToast();
  const [message, setMessage] = useState("");
  const [entryId, setEntryId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = review !== null;
  const result = review?.result;

  const name = result
    ? result.kind === "imaging"
      ? `${(result.modality ?? "").toUpperCase()} ${result.body_part ?? ""}`.trim()
      : friendlyTestName(result.test_name, t)
    : "";
  const shown = result
    ? result.kind === "imaging"
      ? ""
      : `${result.value ?? ""}${result.unit ? ` ${result.unit}` : ""}`
    : "";

  // A fresh suggestion for each result, never a leftover from the last one. It
  // follows the language until the clinician has typed something of their own:
  // their words are never replaced.
  const touched = useRef(false);
  const shownFor = useRef<string | null>(null);
  useEffect(() => {
    if (!review) {
      shownFor.current = null;
      return;
    }
    const isNew = shownFor.current !== review.id;
    if (isNew) {
      shownFor.current = review.id;
      touched.current = false;
      setEntryId("");
      setError(null);
    }
    if (isNew || !touched.current) {
      setMessage(
        t(review.result.kind === "imaging" ? "inform.suggestion.imaging" : "inform.suggestion")
          .replace("{test}", name)
          .replace("{value}", shown),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [review?.id, lang]);

  const { data: entries } = useQuery({
    queryKey: ["results", "shareable", review?.patient_id],
    queryFn: () => api.shareableEvents(review!.patient_id),
    enabled: open,
  });
  const available = (entries ?? []).filter((e) => !e.already_shared);

  const send = async () => {
    if (!review || !message.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.communicateResult(review.id, {
        message: message.trim(),
        ...(entryId ? { timeline_event_id: Number(entryId) } : {}),
      });
      showToast(t(updated.patient_notified ? "inform.done" : "inform.doneNoPortal"));
      onDone(updated);
    } catch (err) {
      setError(t(err instanceof ApiError && err.status === 409 ? "inform.error.conflict" : "inform.error.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={t("inform.title")}>
      {review && result ? (
        <div className="space-y-4">
          <div className="card space-y-1 py-3 text-sm">
            <div className="font-semibold">{name}</div>
            {shown ? <div>{shown}</div> : null}
            <div className="text-xs text-muted">
              {review.patient_name ? `${review.patient_name} · ` : ""}
              {t(`results.disposition.${review.disposition ?? "needs_patient_contact"}`)}
            </div>
          </div>

          <div>
            <label htmlFor="inform-message" className="mb-1 block text-sm font-semibold">
              {t("inform.message")}
            </label>
            <textarea
              id="inform-message"
              value={message}
              maxLength={MAX_MESSAGE}
              onChange={(e) => {
                touched.current = true;
                setMessage(e.target.value);
              }}
              rows={6}
              className="input"
              aria-describedby="inform-message-hint"
            />
            <div id="inform-message-hint" className="mt-1 flex justify-between gap-3 text-xs text-muted">
              <span>{t("inform.messageHint")}</span>
              <span className="shrink-0">
                {message.length.toLocaleString(lang)} / {MAX_MESSAGE.toLocaleString(lang)}
              </span>
            </div>
          </div>

          {available.length > 0 ? (
            <div>
              <label htmlFor="inform-entry" className="mb-1 block text-sm font-semibold">
                {t("inform.attach")}
              </label>
              <select
                id="inform-entry"
                value={entryId}
                onChange={(e) => setEntryId(e.target.value)}
                className="input min-w-0"
              >
                <option value="">{t("inform.attachNone")}</option>
                {available.map((e) => (
                  <option key={e.timeline_event_id} value={e.timeline_event_id}>
                    {e.title} · {e.date}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          ) : null}

          <div className="flex gap-2">
            <button type="button" onClick={onClose} disabled={busy} className="btn-ghost tap flex-1">
              {t("inform.cancel")}
            </button>
            <button
              type="button"
              onClick={send}
              disabled={busy || !message.trim()}
              className="btn-primary tap flex-1 disabled:opacity-50"
            >
              {busy ? t("inform.sending") : t("inform.send")}
            </button>
          </div>
        </div>
      ) : null}
    </Sheet>
  );
}
