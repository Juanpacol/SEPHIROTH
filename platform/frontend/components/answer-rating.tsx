"use client";

import { useId, useState } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { api, type Rating, type RatingReason } from "@/lib/api";
import { useLanguage } from "@/lib/language";

const REASONS: RatingReason[] = ["incorrect", "incomplete", "unsafe", "no_sources", "other"];
const MAX_COMMENT = 500;

type Mode = "idle" | "asking" | "saved";

/** Useful / not useful on one answer. "Not useful" asks why before it saves,
 * since the reason is what makes the rating actionable in the review queue;
 * "useful" saves on the click. A saved rating can be changed — rating again
 * replaces it on the server.
 *
 * Only rendered once the consultation has an id (the `persisted` event), so a
 * rating always has a consultation to belong to. */
export default function AnswerRating({
  consultationId,
  initial = null,
}: {
  consultationId: string;
  initial?: Rating | null;
}) {
  const { t } = useLanguage();
  const [mode, setMode] = useState<Mode>(initial ? "saved" : "idle");
  const [saved, setSaved] = useState<Rating | null>(initial);
  const [reason, setReason] = useState<RatingReason | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const commentId = useId();

  const save = async (body: { value: "up" | "down"; reason?: RatingReason; comment?: string }) => {
    setBusy(true);
    setError(false);
    try {
      setSaved(await api.rateConsultation(consultationId, body));
      setMode("saved");
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  const button =
    "tap inline-flex items-center justify-center gap-1.5 rounded-full px-3 text-xs font-semibold ring-1 ring-line/70 hover:bg-surface hover:text-primary disabled:opacity-50";

  return (
    <div className="space-y-2 border-t border-line/60 pt-3" data-testid="answer-rating">
      {mode === "saved" && saved ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted" role="status">
          {saved.value === "up" ? <ThumbsUp size={13} /> : <ThumbsDown size={13} />}
          <span>{t("rating.thanks")}</span>
          <button type="button" className="tap font-semibold text-primary" onClick={() => setMode("idle")}>
            {t("rating.change")}
          </button>
        </div>
      ) : mode === "asking" ? (
        <div className="space-y-2">
          <div className="text-xs font-semibold" id={`${commentId}-why`}>
            {t("rating.whyTitle")}
          </div>
          <div role="radiogroup" aria-labelledby={`${commentId}-why`} className="flex flex-wrap gap-1.5">
            {REASONS.map((r) => (
              <button
                key={r}
                type="button"
                role="radio"
                aria-checked={reason === r}
                onClick={() => setReason(r)}
                className={`tap rounded-full px-3 text-xs font-semibold ring-1 ${
                  reason === r ? "bg-primary text-white ring-primary" : "ring-line/70 hover:bg-surface"
                }`}
              >
                {t(`rating.reason.${r}`)}
              </button>
            ))}
          </div>
          <label htmlFor={commentId} className="block text-xs text-muted">
            {t("rating.comment")}
          </label>
          <textarea
            id={commentId}
            value={comment}
            maxLength={MAX_COMMENT}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            className="block w-full min-w-0 rounded-lg bg-surface p-2 text-sm outline-none ring-1 ring-line/70 focus:ring-primary/50"
          />
          <div className="text-[11px] text-muted">{t("rating.commentHint")}</div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              className={`${button} bg-primary text-white !ring-primary hover:!text-white`}
              onClick={() => save({ value: "down", reason: reason ?? undefined, comment: comment.trim() })}
            >
              {t("rating.send")}
            </button>
            <button type="button" disabled={busy} className={button} onClick={() => setMode("idle")}>
              {t("rating.cancel")}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">{t("rating.prompt")}</span>
          <button type="button" disabled={busy} className={button} onClick={() => save({ value: "up" })}>
            <ThumbsUp size={13} /> {t("rating.up")}
          </button>
          <button type="button" disabled={busy} className={button} onClick={() => setMode("asking")}>
            <ThumbsDown size={13} /> {t("rating.down")}
          </button>
        </div>
      )}
      {error && (
        <div role="alert" className="text-xs text-danger">
          {t("rating.error")}
        </div>
      )}
    </div>
  );
}
