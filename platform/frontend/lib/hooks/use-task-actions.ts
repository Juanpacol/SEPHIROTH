"use client";

/** Acting on a task, optimistically, with a way back.
 *
 * Resolving and dismissing remove the row from the list immediately — waiting
 * on a round-trip before a row disappears makes an inbox feel broken. That is
 * only safe because the toast carries an undo: on a phone, a mis-tap otherwise
 * closes clinical work with no way to find it again short of changing the
 * filter, and "where did that go" is how people stop trusting an inbox.
 *
 * The rollback is the standard cancel-snapshot-restore dance. It matters more
 * than usual here: an optimistic remove that fails silently leaves a clinician
 * believing they handled something they did not.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, type ClinicalTask } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { useToast } from "@/components/ui/toast";
import { BADGES_QUERY_KEY } from "./use-badge-counts";

export const TASKS_QUERY_KEY = ["tasks"] as const;

export type TaskAction =
  | { kind: "claim" }
  | { kind: "resume" }
  | { kind: "complete" }
  | { kind: "reopen" }
  | { kind: "snooze"; until: string }
  | { kind: "dismiss"; reason: string }
  | { kind: "assign"; assigneeId: string }
  | { kind: "comment"; body: string };

/** Actions after which the row should leave the current list straight away. */
const REMOVES_ROW = new Set(["complete", "dismiss", "snooze"]);

const UNDO_MS = 6000;

function perform(taskId: string, action: TaskAction): Promise<ClinicalTask> {
  switch (action.kind) {
    case "claim":
      return api.claimTask(taskId);
    case "resume":
      return api.resumeTask(taskId);
    case "complete":
      return api.completeTask(taskId);
    case "reopen":
      return api.reopenTask(taskId);
    case "snooze":
      return api.snoozeTask(taskId, action.until);
    case "dismiss":
      return api.dismissTask(taskId, action.reason);
    case "assign":
      return api.assignTask(taskId, action.assigneeId);
    case "comment":
      return api.commentOnTask(taskId, action.body);
  }
}

export function useTaskAction() {
  const client = useQueryClient();
  const showToast = useToast();
  const { t } = useLanguage();

  return useMutation({
    mutationFn: ({ taskId, action }: { taskId: string; action: TaskAction }) =>
      perform(taskId, action),

    onMutate: async ({ taskId, action }) => {
      if (!REMOVES_ROW.has(action.kind)) return { snapshots: [] };

      await client.cancelQueries({ queryKey: TASKS_QUERY_KEY });
      const snapshots = client.getQueriesData({ queryKey: TASKS_QUERY_KEY });

      client.setQueriesData({ queryKey: TASKS_QUERY_KEY }, (old: unknown) => {
        const page = old as { items?: ClinicalTask[]; total_count?: number } | undefined;
        if (!page?.items) return old;
        const remaining = page.items.filter((task) => task.id !== taskId);
        return {
          ...page,
          items: remaining,
          total_count: Math.max((page.total_count ?? remaining.length) - 1, 0),
        };
      });

      return { snapshots };
    },

    onError: (error, _variables, context) => {
      // Put every list back exactly as it was — a half-restored inbox is
      // harder to reason about than one that never changed.
      for (const [key, data] of context?.snapshots ?? []) {
        client.setQueryData(key, data);
      }
      const message =
        error instanceof ApiError && error.status === 409
          ? error.message
          : t("tasks.error.generic");
      showToast(message, "error");
    },

    onSuccess: (_task, { taskId, action }) => {
      if (!REMOVES_ROW.has(action.kind)) return;
      showToast(t(`tasks.done.${action.kind}`), "success", {
        durationMs: UNDO_MS,
        action: {
          label: t("common.undo"),
          onClick: () => {
            // The inverse of "it left the list" is "put it back", which for a
            // closed task is reopen and for a snoozed one is resume.
            const inverse: TaskAction = action.kind === "snooze" ? { kind: "resume" } : { kind: "reopen" };
            perform(taskId, inverse)
              .catch(() => showToast(t("tasks.error.undo"), "error"))
              .finally(() => {
                client.invalidateQueries({ queryKey: TASKS_QUERY_KEY });
                client.invalidateQueries({ queryKey: BADGES_QUERY_KEY });
              });
          },
        },
      });
    },

    onSettled: () => {
      client.invalidateQueries({ queryKey: TASKS_QUERY_KEY });
      client.invalidateQueries({ queryKey: BADGES_QUERY_KEY });
    },
  });
}
