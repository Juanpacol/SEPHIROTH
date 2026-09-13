"use client";

/** The right-hand panel of /approvals: read the draft, edit it, approve or
 * reject. Extracted from the page so it can be rendered twice — inline beside
 * the list on a wide screen, and inside a bottom sheet on a phone, where a
 * side-by-side master-detail has nowhere to put the detail. Props only, no
 * state of its own beyond the draft being edited, so the two copies cannot
 * disagree about anything the server owns. */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { api, ApiError, type PendingAction } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { useToast } from "@/components/ui/toast";
import AgentBadge from "@/components/agent-badge";
import StatusPill from "@/components/status-pill";

// The only source of a PendingAction today is a day-3/7/30 follow-up
// check-in (`patient_followup.py::enroll_plan`) — this pulls the day
// number back out of "followup_day7" so it can be shown as a real
// sentence instead of the raw snake_case type. Falls back to a generic
// humanized form for anything else (keeps this from silently breaking
// if a new action type is added later).
const FOLLOWUP_CHECK_RE = /^followup_day(\d+)$/;

export function actionTypeLabel(actionType: string, t: (key: string) => string): string {
  const match = actionType.match(FOLLOWUP_CHECK_RE);
  if (match) return t("approvals.type.followupCheck").replace("{day}", match[1]);
  return actionType.replace(/_/g, " ");
}

export default function ActionDetail({ action, onDone }: { action: PendingAction; onDone: () => void }) {
  const { t } = useLanguage();
  const showToast = useToast();
  const queryClient = useQueryClient();
  const [text, setText] = useState(action.final_text || action.draft_text);
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  // Dropped as soon as the clinician edits: the gradient/badge mark
  // AI-generated prose, and edited text is clinician-authored (CLAUDE.md
  // decision #4) -- leaving the marker on would misattribute it.
  const edited = text !== action.draft_text;
  const who = action.patient_name ?? t("approvals.unknownPatient");

  const draft = useMutation({
    mutationFn: () => api.draftPendingAction(action.id),
    onSuccess: (updated) => setText(updated.draft_text),
    onError: () => showToast(t("approvals.error.generateDraft"), "error"),
  });

  const approve = useMutation({
    mutationFn: () => api.approvePendingAction(action.id, text),
    onSuccess: () => {
      showToast(t("approvals.approved"));
      queryClient.invalidateQueries({ queryKey: ["pending-actions"] });
      onDone();
    },
    onError: (err) =>
      showToast(
        err instanceof ApiError && err.status === 422
          ? t("approvals.error.approveFlagged")
          : t("approvals.error.approve"),
        "error"
      ),
  });

  const reject = useMutation({
    mutationFn: () => api.rejectPendingAction(action.id, rejectReason),
    onSuccess: () => {
      showToast(t("approvals.rejected"));
      queryClient.invalidateQueries({ queryKey: ["pending-actions"] });
      onDone();
    },
    onError: () => showToast(t("approvals.error.reject"), "error"),
  });

  const isPending = action.status === "pending";

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-bold">{who}</h2>
          <p className="text-xs text-muted">{actionTypeLabel(action.action_type, t)}</p>
        </div>
        <div className="flex items-center gap-2">
          {!edited && action.draft_source === "llm" && <AgentBadge name={action.draft_model ?? "AI draft"} />}
          <StatusPill label={action.status} />
        </div>
      </div>

      {isPending && (
        <p className="rounded-xl bg-primary-soft px-3 py-2 text-xs text-ink/80">
          {t("approvals.whatIsThis")
            .replace("{patient}", who)
            .replace("{type}", actionTypeLabel(action.action_type, t).toLowerCase())}
          {action.instructions && (
            <>
              {" "}
              {t("approvals.watchingFor").replace("{instructions}", action.instructions)}
            </>
          )}
        </p>
      )}

      {isPending && action.draft_source === "llm" && !action.draft_text && (
        <button onClick={() => draft.mutate()} disabled={draft.isPending} className="btn-primary">
          {draft.isPending ? t("approvals.drafting") : t("approvals.generateDraft")}
        </button>
      )}

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        readOnly={!isPending}
        rows={5}
        className="input w-full resize-y"
        placeholder={t("approvals.emptyDraft")}
      />

      {isPending && (
        <div className="space-y-2">
          {showReject ? (
            <div className="space-y-2">
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={2}
                placeholder={t("approvals.reasonPlaceholder")}
                className="input w-full resize-y"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => reject.mutate()}
                  disabled={reject.isPending || rejectReason.trim() === ""}
                  className="rounded-xl bg-danger px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
                >
                  {t("approvals.confirmReject")}
                </button>
                <button onClick={() => setShowReject(false)} className="text-sm text-muted">
                  {t("approvals.cancel")}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={() => approve.mutate()}
                disabled={approve.isPending || text.trim() === ""}
                className="btn-primary flex items-center gap-1.5"
              >
                <CheckCircle2 size={15} /> {t("approvals.approve")}
              </button>
              <button
                onClick={() => setShowReject(true)}
                className="flex items-center gap-1.5 rounded-xl border border-line/70 px-4 py-2 text-sm font-semibold text-danger"
              >
                <XCircle size={15} /> {t("approvals.reject")}
              </button>
            </div>
          )}
        </div>
      )}

      {action.status === "rejected" && action.reject_reason && (
        <p className="text-xs text-muted">
          {t("approvals.rejectedReason")}: {action.reject_reason}
        </p>
      )}
    </div>
  );
}
