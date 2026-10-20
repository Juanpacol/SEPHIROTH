"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { friendlyTestName } from "@/lib/clinical-text";
import { buildLabRows, type LabRow, type LabStatus } from "@/lib/lab-rows";
import { type LabReviewState } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import MiniTrend from "@/components/dashboard/mini-trend";
import RecordLabSheet from "@/components/patients/record-lab-sheet";

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

const REVIEW_STYLE: Record<LabReviewState["status"], string> = {
  received: "bg-warning/10 text-warning",
  reviewed: "bg-primary-soft text-primary",
  communicated: "bg-success/10 text-success",
  closed: "bg-surface text-muted",
};

/** Where a result stands in its review, in words, with a way to the inbox. A
 * result nobody has reviewed yet stands out when it is critical. Nothing is
 * drawn for a result with no review: "not reviewed" would promise an inbox
 * item that does not exist. */
function ReviewLine({ row, patientId }: { row: LabRow; patientId: string }) {
  const { t, lang } = useLanguage();
  const review = row.review;
  if (!review) return null;
  const date = (iso: string) => new Date(iso).toLocaleDateString(lang);
  const urgent = review.status === "received" && row.status === "critical";
  const details = [
    review.disposition ? t(`results.disposition.${review.disposition}`) : null,
    review.reviewed_by,
    review.reviewed_at ? date(review.reviewed_at) : null,
    review.communicated_at ? t("labs.review.told").replace("{date}", date(review.communicated_at)) : null,
  ].filter(Boolean);
  const filter = review.status === "closed" ? "closed" : "open";

  return (
    <div className="mt-1 space-y-0.5 text-xs" data-testid="lab-review">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span
          className={`rounded-full px-2 py-0.5 font-semibold ${urgent ? "bg-danger/10 text-danger ring-1 ring-danger/30" : REVIEW_STYLE[review.status]}`}
        >
          {t(`labs.review.${review.status}`)}
        </span>
        <Link
          href={`/results?patient=${encodeURIComponent(patientId)}&filter=${filter}`}
          className="tap inline-flex items-center font-semibold text-primary"
        >
          {t("labs.review.open")}
        </Link>
      </div>
      {details.length > 0 ? <div className="text-muted">{details.join(" · ")}</div> : null}
    </div>
  );
}

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
  const [recording, setRecording] = useState(false);
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
      <div className="mb-1 flex items-center justify-between gap-3">
        <h2 className="min-w-0 font-bold">{t("labs.card.title")}</h2>
        <button type="button" onClick={() => setRecording(true)} className="btn-ghost tap shrink-0 text-sm">
          {t("recordLab.open")}
        </button>
      </div>
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
                <ReviewLine row={row} patientId={patientId} />
              </li>
            );
          })}
        </ul>
      )}
      {/* Mounted only while open: it needs the toast provider and the catalog, and
          a closed sheet has no use for either. */}
      {recording ? <RecordLabSheet patientId={patientId} open onClose={() => setRecording(false)} /> : null}
    </div>
  );
}
