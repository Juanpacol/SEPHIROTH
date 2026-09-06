"use client";

/** Every follow-up plan across the panel (SPEC-019).
 *
 * `GET /api/followups` existed and was only reachable through one patient's
 * chart, which makes "who is on a follow-up plan right now" a question you can
 * only answer by opening patients one at a time.
 *
 * Cancelling from here is deliberately not offered: cancelling a plan is a
 * clinical decision about one patient, and it belongs next to that patient's
 * chart, not in a list where the row above and below belong to someone else.
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { api, type FollowupPlan } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import DataList, { type Column } from "@/components/ui/data-list";
import SegmentedControl from "@/components/ui/segmented-control";
import StatusPill from "@/components/status-pill";

type Scope = "active" | "all";

export default function FollowupsPage() {
  const { t } = useLanguage();
  const [scope, setScope] = useState<Scope>("active");

  const { data: plans, isLoading } = useQuery({
    queryKey: ["followups", scope],
    queryFn: () => api.listFollowupPlans(scope === "active" ? { status: "active" } : undefined),
  });
  const { data: patients } = useQuery({ queryKey: ["patients", "name"], queryFn: () => api.patients() });

  const nameFor = useMemo(() => {
    const map = new Map((patients ?? []).map((p) => [p.id, p.name]));
    return (id: string) => map.get(id) ?? id;
  }, [patients]);

  const columns: Column<FollowupPlan>[] = useMemo(
    () => [
      {
        key: "patient",
        header: t("followups.column.patient"),
        primary: true,
        render: (plan) => (
          <Link href={`/patients/${plan.patient_id}`} className="font-semibold hover:text-primary">
            {nameFor(plan.patient_id)}
          </Link>
        ),
      },
      {
        key: "instructions",
        header: t("followups.column.instructions"),
        desktopOnly: true,
        className: "max-w-sm",
        render: (plan) => <span className="block truncate text-muted">{plan.instructions || "—"}</span>,
      },
      {
        key: "started",
        header: t("followups.column.started"),
        render: (plan) => new Date(plan.created_at).toLocaleDateString(),
      },
      {
        key: "status",
        header: t("followups.column.status"),
        render: (plan) => <StatusPill label={plan.status} />,
      },
    ],
    [t, nameFor],
  );

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("followups.title")}</h1>
        <p className="text-sm text-muted">{t("followups.subtitle")}</p>
      </div>

      <SegmentedControl<Scope>
        label={t("followups.filter.scope")}
        value={scope}
        onChange={setScope}
        options={[
          { value: "active", label: t("followups.filter.active") },
          { value: "all", label: t("followups.filter.all") },
        ]}
      />

      <DataList
        items={plans ?? []}
        columns={columns}
        rowKey={(plan) => plan.id}
        isLoading={isLoading}
        loadingLabel={t("followups.loading")}
        emptyLabel={t("followups.empty")}
        caption={t("followups.title")}
      />
    </div>
  );
}
