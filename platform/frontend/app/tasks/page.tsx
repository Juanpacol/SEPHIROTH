"use client";

/** The clinical task inbox (SPEC-018).
 *
 * Filters live in the URL rather than in component state, so a filtered inbox
 * is a link someone can send ("the overdue criticals") and so the React Query
 * key derives from the address bar instead of a second source of truth.
 *
 * Layout by width, all of it CSS: cards below `md`, a table above it (both from
 * `DataList`'s single column set), with the row menu becoming a bottom sheet on
 * a phone because a dropdown anchored to a 24px glyph is not a thumb target.
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { MoreHorizontal } from "lucide-react";

import { api, type ClinicalTask, type TaskSeverity } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { useTaskAction, TASKS_QUERY_KEY } from "@/lib/hooks/use-task-actions";
import DataList, { type Column } from "@/components/ui/data-list";
import DropdownMenu, { type MenuItem } from "@/components/ui/dropdown-menu";
import SegmentedControl from "@/components/ui/segmented-control";
import Dialog from "@/components/ui/dialog";
import StatusPill from "@/components/status-pill";

type Scope = "mine" | "unassigned" | "all";

const SCOPE_TO_ASSIGNEE: Record<Scope, string | undefined> = {
  mine: "me",
  unassigned: "unassigned",
  all: undefined,
};

const SEVERITY_TONE: Record<TaskSeverity, string> = {
  critical: "bg-danger",
  high: "bg-warning",
  medium: "bg-primary",
  low: "bg-line",
};

/** Snooze presets, in hours. Anything longer than the service's 7-day cap
 * would be refused, so the menu does not offer it. */
const SNOOZE_PRESETS: { key: string; hours: number }[] = [
  { key: "1h", hours: 1 },
  { key: "tonight", hours: 8 },
  { key: "tomorrow", hours: 24 },
  { key: "nextWeek", hours: 24 * 6 },
];

export default function TasksPage() {
  const { t } = useLanguage();
  const router = useRouter();
  const params = useSearchParams();
  const act = useTaskAction();

  const scope = (params.get("scope") as Scope) || "all";
  const severity = params.get("severity") as TaskSeverity | null;
  const overdue = params.get("overdue") === "1";

  const [dismissing, setDismissing] = useState<ClinicalTask | null>(null);
  const [dismissReason, setDismissReason] = useState("");

  const filters = useMemo(
    () => ({
      status: ["open", "in_progress", "snoozed"] as const,
      assignee: SCOPE_TO_ASSIGNEE[scope],
      severity: severity ?? undefined,
      overdue: overdue || undefined,
      sort: "priority" as const,
      limit: 50,
    }),
    [scope, severity, overdue],
  );

  const { data, isLoading, isError, refetch } = useQuery({
    // Derived from the URL, so the address bar and the cache cannot disagree.
    queryKey: [...TASKS_QUERY_KEY, filters],
    queryFn: () => api.listTasks({ ...filters, status: [...filters.status] }),
    refetchInterval: 60_000,
  });

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (value === null) next.delete(key);
    else next.set(key, value);
    router.replace(`/tasks${next.toString() ? `?${next}` : ""}`, { scroll: false });
  };

  const menuFor = (task: ClinicalTask): MenuItem[] => {
    const items: MenuItem[] = [];
    if (task.status === "open") {
      items.push({ label: t("tasks.action.claim"), onSelect: () => act.mutate({ taskId: task.id, action: { kind: "claim" } }) });
    }
    if (task.status === "snoozed") {
      items.push({ label: t("tasks.action.resume"), onSelect: () => act.mutate({ taskId: task.id, action: { kind: "resume" } }) });
    }
    if (task.completable) {
      items.push({ label: t("tasks.action.complete"), onSelect: () => act.mutate({ taskId: task.id, action: { kind: "complete" } }) });
    }
    if (task.severity !== "critical" && task.status !== "snoozed") {
      for (const preset of SNOOZE_PRESETS) {
        items.push({
          label: t(`tasks.snooze.${preset.key}`),
          onSelect: () =>
            act.mutate({
              taskId: task.id,
              action: {
                kind: "snooze",
                until: new Date(Date.now() + preset.hours * 3600_000).toISOString(),
              },
            }),
        });
      }
    }
    items.push({
      label: t("tasks.action.dismiss"),
      destructive: true,
      onSelect: () => {
        setDismissReason("");
        setDismissing(task);
      },
    });
    return items;
  };

  const columns: Column<ClinicalTask>[] = useMemo(
    () => [
      {
        key: "title",
        header: t("tasks.column.task"),
        primary: true,
        render: (task) => (
          <span className="flex items-start gap-2">
            <span
              aria-hidden="true"
              className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEVERITY_TONE[task.severity]}`}
            />
            <span className="min-w-0">
              <Link href={`/tasks?focus=${task.id}`} className="font-semibold hover:text-primary">
                {task.title}
              </Link>
              {task.patient_name && task.patient_id && (
                <Link
                  href={`/patients/${task.patient_id}`}
                  className="block text-xs text-muted hover:text-primary"
                >
                  {task.patient_name}
                </Link>
              )}
            </span>
          </span>
        ),
      },
      {
        key: "severity",
        header: t("tasks.column.severity"),
        render: (task) => <StatusPill label={task.severity} />,
      },
      {
        key: "due",
        header: t("tasks.column.due"),
        render: (task) => {
          if (!task.due_at) return "—";
          const due = new Date(task.due_at);
          const late = due.getTime() < Date.now();
          return (
            <span className={late ? "font-semibold text-danger" : "text-muted"}>
              {due.toLocaleDateString()}
            </span>
          );
        },
      },
      {
        key: "status",
        header: t("tasks.column.status"),
        render: (task) => t(`tasks.status.${task.status}`),
      },
      {
        key: "actions",
        header: t("tasks.column.actions"),
        render: (task) => (
          <DropdownMenu
            label={t("tasks.action.menu")}
            trigger={<MoreHorizontal size={18} />}
            items={menuFor(task)}
          />
        ),
      },
    ],
    // `act` and `t` are stable enough for this list; recreating the columns on
    // every render would rebuild every dropdown.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, scope, severity, overdue],
  );

  if (isError) {
    return (
      <div className="card space-y-3">
        <p className="text-sm text-danger">{t("tasks.error.load")}</p>
        <button type="button" className="btn-secondary" onClick={() => refetch()}>
          {t("common.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("tasks.title")}</h1>
        <p className="text-sm text-muted">{t("tasks.subtitle")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl<Scope>
          label={t("tasks.filter.scope")}
          value={scope}
          onChange={(next) => setParam("scope", next === "all" ? null : next)}
          options={[
            { value: "mine", label: t("tasks.filter.mine") },
            { value: "unassigned", label: t("tasks.filter.unassigned") },
            { value: "all", label: t("tasks.filter.all") },
          ]}
        />
        <button
          type="button"
          onClick={() => setParam("overdue", overdue ? null : "1")}
          aria-pressed={overdue}
          className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
            overdue ? "bg-danger text-white" : "bg-surface text-muted hover:text-primary"
          }`}
        >
          {t("tasks.filter.overdue")}
        </button>
        {(["critical", "high", "medium", "low"] as TaskSeverity[]).map((level) => (
          <button
            key={level}
            type="button"
            onClick={() => setParam("severity", severity === level ? null : level)}
            aria-pressed={severity === level}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
              severity === level ? "bg-primary text-white" : "bg-surface text-muted hover:text-primary"
            }`}
          >
            {t(`tasks.severity.${level}`)}
          </button>
        ))}
      </div>

      <DataList
        items={data?.items ?? []}
        columns={columns}
        rowKey={(task) => task.id}
        isLoading={isLoading}
        loadingLabel={t("tasks.loading")}
        emptyLabel={
          scope === "all" && !severity && !overdue ? t("tasks.empty.all") : t("tasks.empty.filtered")
        }
        caption={t("tasks.title")}
      />

      {data && data.has_more && (
        <p className="text-center text-xs text-muted">
          {t("tasks.showingOf")
            .replace("{shown}", String(data.items.length))
            .replace("{total}", String(data.total_count))}
        </p>
      )}

      <Dialog
        open={dismissing !== null}
        onClose={() => setDismissing(null)}
        title={t("tasks.dismiss.title")}
        description={t("tasks.dismiss.description")}
        confirmLabel={t("tasks.action.dismiss")}
        destructive
        confirmDisabled={dismissReason.trim().length === 0}
        onConfirm={() => {
          if (!dismissing) return;
          act.mutate({ taskId: dismissing.id, action: { kind: "dismiss", reason: dismissReason.trim() } });
          setDismissing(null);
        }}
      >
        {/* Required, not optional: dismissing is closing clinical work without
            doing it, and the reason is the audit trail's only account of why. */}
        <label className="block text-sm font-medium">
          {t("tasks.dismiss.reasonLabel")}
          <input
            value={dismissReason}
            onChange={(e) => setDismissReason(e.target.value)}
            className="input mt-1"
            maxLength={300}
            autoFocus
          />
        </label>
      </Dialog>
    </div>
  );
}
