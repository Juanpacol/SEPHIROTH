"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import ActionDetail, { actionTypeLabel } from "@/components/approvals/action-detail";
import FilterTabs from "@/components/ui/filter-tabs";
import PageHeader from "@/components/ui/page-header";
import Sheet from "@/components/ui/sheet";

const STATUS_FILTERS = ["pending", "approved", "rejected", "expired"] as const;

export default function ApprovalsPage() {
  const { t } = useLanguage();
  const [status, setStatus] = useState<(typeof STATUS_FILTERS)[number]>("pending");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: actions, isLoading } = useQuery({
    queryKey: ["pending-actions", status],
    queryFn: () => api.listPendingActions({ status }),
  });

  const picked = actions?.find((a) => a.id === selectedId) ?? null;
  // Wide screens show something in the detail column from the moment the list
  // loads; a phone must not, or the bottom sheet would slam open by itself on
  // arrival. So the two shapes read different values: the sheet is driven by an
  // explicit pick, the inline panel falls back to the first row.
  const inlineSelected = picked ?? actions?.[0] ?? null;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PageHeader
        eyebrow={t("patients.eyebrow")}
        title={t("approvals.title")}
        subtitle={t("approvals.subtitle")}
      />

      <FilterTabs
        label={t("approvals.title")}
        value={status}
        onChange={(f) => {
          setStatus(f);
          setSelectedId(null);
        }}
        tabs={STATUS_FILTERS.map((f) => ({ value: f, label: t(`approvals.status.${f}`) }))}
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-[280px_minmax(0,1fr)]">
        <div className="space-y-1">
          {isLoading && <p className="text-sm text-muted">{t("approvals.loading")}</p>}
          {actions?.length === 0 && (
            <p className="card text-sm text-muted">{t(`approvals.empty.${status}`)}</p>
          )}
          {actions?.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedId(a.id)}
              aria-current={inlineSelected?.id === a.id ? "true" : undefined}
              className={`tap relative w-full rounded-xl py-2.5 pl-4 pr-3 text-left transition-colors duration-normal ${
                inlineSelected?.id === a.id ? "bg-primary-soft/50" : "hover:bg-primary-soft/25"
              }`}
            >
              <span
                aria-hidden
                className={`absolute inset-y-2.5 left-0 w-0.5 rounded-full bg-primary-ink transition-transform duration-300 ${
                  inlineSelected?.id === a.id ? "scale-y-100" : "scale-y-0"
                }`}
              />
              <p className="text-sm font-semibold">{a.patient_name ?? t("approvals.unknownPatient")}</p>
              <p className="eyebrow text-muted">{actionTypeLabel(a.action_type, t)}</p>
            </button>
          ))}
        </div>

        {/* Dual shell. Both copies exist in the DOM and CSS picks which one is
            visible — the sheet is `fixed`, so hiding its wrapper is enough and
            neither shape needs a media query in JavaScript. Same trade as
            `components/ui/data-list.tsx`: a duplicated subtree, bought for the
            guarantee that the two cannot drift. */}
        <div className="hidden md:block">
          {inlineSelected ? (
            <ActionDetail
              key={inlineSelected.id}
              action={inlineSelected}
              onDone={() => setSelectedId(null)}
            />
          ) : (
            !isLoading && <p className="card text-sm text-muted">{t("approvals.selectOne")}</p>
          )}
        </div>

        <div className="md:hidden">
          <Sheet
            open={picked !== null}
            onClose={() => setSelectedId(null)}
            side="bottom"
            title={picked?.patient_name ?? t("approvals.unknownPatient")}
          >
            {picked && <ActionDetail key={picked.id} action={picked} onDone={() => setSelectedId(null)} />}
          </Sheet>
        </div>
      </div>
    </div>
  );
}
