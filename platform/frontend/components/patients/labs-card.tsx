"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { friendlyTestName } from "@/lib/clinical-text";
import { buildLabRows, type LabRow, type LabStatus } from "@/lib/lab-rows";
import { useLanguage } from "@/lib/language";
import MiniTrend from "@/components/dashboard/mini-trend";

const STATUS_STYLE: Record<LabStatus, string> = {
  critical: "bg-danger/10 text-danger",
  high: "bg-warning/10 text-warning",
  low: "bg-warning/10 text-warning",
  abnormal: "bg-warning/10 text-warning",
  normal: "bg-success/10 text-success",
  unknown: "",
};

const VALUE_STYLE: Record<LabStatus, string> = {
  critical: "text-danger",
  high: "text-warning",
  low: "text-warning",
  abnormal: "text-warning",
  normal: "",
  unknown: "",
};

/** One patient's labs, one row per test, worst first. Replaces the two cards
 * that used to describe the same thing from different sources: see
 * `lib/lab-rows.ts` for how they are merged. */
export default function LabsCard({
  patientId,
  snapshot,
}: {
  patientId: string;
  /** `Patient.lab_results`: the latest value as text, for a test with no history. */
  snapshot: Record<string, string>;
}) {
  const { t, lang } = useLanguage();
  const { data, isLoading } = useQuery({
    queryKey: ["patient-lab-history", patientId],
    queryFn: () => api.patientLabHistory(patientId),
  });

  const rows = useMemo(
    () => buildLabRows(data, snapshot, (name) => friendlyTestName(name, t)),
    [data, snapshot, t],
  );

  const date = (iso: string) => new Date(iso).toLocaleDateString(lang);

  function range(row: LabRow): string | null {
    // A non-breaking space keeps "5.7 %" from wrapping with the unit alone on a line.
    const unit = row.unit ? `\u00a0${row.unit}` : "";
    if (row.low != null && row.high != null) return `${row.low}–${row.high}${unit}`;
    if (row.high != null) return `≤ ${row.high}${unit}`;
    if (row.low != null) return `≥ ${row.low}${unit}`;
    return null;
  }

  return (
    <div className="card" data-testid="labs-card">
      <h2 className="mb-1 font-bold">{t("labs.card.title")}</h2>
      <p className="mb-3 text-xs text-muted">{t("labs.card.subtitle")}</p>
      {isLoading ? (
        <p className="text-sm text-muted">{t("labs.card.loading")}</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">{t("labs.card.empty")}</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row) => {
            const name = friendlyTestName(row.testName, t);
            const reference = range(row);
            return (
              <li key={row.key}>
                {/* Same two lines for every row, at every width: what it is and its
                    value, then when, against what, and how it is doing. */}
                <div className="flex items-baseline justify-between gap-3">
                  <div className="min-w-0 text-sm font-semibold">{name}</div>
                  <span className={`shrink-0 text-sm font-semibold ${VALUE_STYLE[row.status]}`}>
                    {row.value}
                    {row.unit ? ` ${row.unit}` : ""}
                  </span>
                </div>
                <div className="mt-0.5 flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 text-xs text-muted">
                    <span>
                      {row.hasHistory && row.takenAt
                        ? `${date(row.takenAt)}${
                            row.readings.length > 1 ? ` · ${row.readings.length} ${t("labs.card.readings")}` : ""
                          }`
                        : t("labs.card.noHistory")}
                    </span>
                    {reference && (
                      <>
                        <span aria-hidden="true"> · </span>
                        <span>
                          {t("labs.card.reference").split("{range}")[0]}
                          <span className="whitespace-nowrap">{reference}</span>
                        </span>
                      </>
                    )}
                  </div>
                  {row.status !== "unknown" && (
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[row.status]}`}
                    >
                      {t(`labs.status.${row.status}`)}
                    </span>
                  )}
                </div>
                <MiniTrend
                  values={row.readings.map((r) => r.value)}
                  lastTone={row.status === "critical" ? "danger" : row.status === "normal" ? "neutral" : "warning"}
                  label={`${name}: ${row.readings.map((r) => `${r.value} (${date(r.takenAt)})`).join(" → ")}`}
                />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
