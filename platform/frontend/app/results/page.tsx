"use client";

/** Every result shared with a patient, in one list (SPEC-019).
 *
 * `GET /api/results/shares` has existed since the results phase and had no
 * clinician-facing page: the only way to see a share was to open the patient
 * it belonged to, which answers "what did I send this person" and never
 * "what is still unread across the panel".
 *
 * `viewed_at` is the column that earns the page. A shared result nobody opened
 * is the failure mode this feature has — the sharing worked and the
 * communication did not.
 */

import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { api, type ResultShare } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import DataList, { type Column } from "@/components/ui/data-list";
import StatusPill from "@/components/status-pill";

export default function ResultsPage() {
  const { t } = useLanguage();

  const { data: shares, isLoading } = useQuery({
    queryKey: ["results", "shares"],
    queryFn: () => api.listShares(),
  });
  // Names are not on the share payload, and adding them there would change a
  // response the patient portal also reads. One extra request, joined here.
  const { data: patients } = useQuery({ queryKey: ["patients", "name"], queryFn: () => api.patients() });

  const nameFor = useMemo(() => {
    const map = new Map((patients ?? []).map((p) => [p.id, p.name]));
    return (id: string | undefined) => (id ? (map.get(id) ?? id) : "—");
  }, [patients]);

  const columns: Column<ResultShare>[] = useMemo(
    () => [
      {
        key: "event",
        header: t("results.column.result"),
        primary: true,
        render: (share) => (
          <span className="min-w-0">
            <span className="block font-semibold">{share.event.title}</span>
            <span className="block text-xs text-muted">{nameFor(share.patient_id)}</span>
          </span>
        ),
      },
      {
        key: "sharedAt",
        header: t("results.column.sharedAt"),
        render: (share) => new Date(share.shared_at).toLocaleDateString(),
      },
      {
        key: "viewed",
        header: t("results.column.viewed"),
        render: (share) =>
          share.viewed_at ? (
            <span className="text-muted">{new Date(share.viewed_at).toLocaleDateString()}</span>
          ) : (
            // The point of the page: shared is not the same as seen.
            <span className="font-semibold text-warning">{t("results.notViewed")}</span>
          ),
      },
      {
        key: "status",
        header: t("results.column.status"),
        render: (share) => <StatusPill label={share.status} />,
      },
      {
        key: "open",
        header: t("results.column.patient"),
        desktopOnly: true,
        render: (share) =>
          share.patient_id ? (
            <Link href={`/patients/${share.patient_id}`} className="text-primary hover:underline">
              {t("results.openPatient")}
            </Link>
          ) : null,
      },
    ],
    [t, nameFor],
  );

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("results.title")}</h1>
        <p className="text-sm text-muted">{t("results.subtitle")}</p>
      </div>

      <DataList
        items={shares ?? []}
        columns={columns}
        rowKey={(share) => share.id}
        isLoading={isLoading}
        loadingLabel={t("results.loading")}
        emptyLabel={t("results.empty")}
        caption={t("results.title")}
      />
    </div>
  );
}
