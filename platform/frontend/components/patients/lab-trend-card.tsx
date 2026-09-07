"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type LabHistoryEntry } from "@/lib/api";
import { useLanguage } from "@/lib/language";

const SPARK_WIDTH = 96;
const SPARK_HEIGHT = 24;
const SPARK_PADDING = 3;

/** A minimal trend line, oldest -> newest left to right. `entries` arrives
 * newest-first (matches how a clinician reads the list below it), so this
 * reverses just for the drawing. Values, not the API's already-decided
 * abnormal/critical flags, drive the axis -- a single wildly abnormal point
 * would otherwise flatten every other point on the line, which is exactly
 * the kind of number a clinician needs to still be able to read. */
function Sparkline({ entries }: { entries: LabHistoryEntry[] }) {
  if (entries.length < 2) return null;
  const chronological = [...entries].reverse();
  const values = chronological.map((e) => e.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const innerW = SPARK_WIDTH - SPARK_PADDING * 2;
  const innerH = SPARK_HEIGHT - SPARK_PADDING * 2;
  const points = chronological
    .map((e, i) => {
      const x = SPARK_PADDING + (i / (chronological.length - 1)) * innerW;
      const y = SPARK_PADDING + innerH - ((e.value - min) / span) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const last = chronological[chronological.length - 1];
  const lastX = SPARK_PADDING + innerW;
  const lastY = SPARK_PADDING + innerH - ((last.value - min) / span) * innerH;

  return (
    <svg
      width={SPARK_WIDTH}
      height={SPARK_HEIGHT}
      viewBox={`0 0 ${SPARK_WIDTH} ${SPARK_HEIGHT}`}
      className="shrink-0"
      role="img"
      aria-label={`Trend: ${chronological.map((e) => e.value).join(" → ")}`}
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        className="text-ink/30"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx={lastX}
        cy={lastY}
        r={2}
        className={last.is_critical ? "fill-danger" : last.is_abnormal ? "fill-warning" : "fill-ink/50"}
      />
    </svg>
  );
}

export default function LabTrendCard({ patientId }: { patientId: string }) {
  const { t } = useLanguage();
  const { data, isLoading } = useQuery({
    queryKey: ["patient-lab-history", patientId],
    queryFn: () => api.patientLabHistory(patientId),
  });

  const tests = data?.tests ?? [];

  return (
    <div className="card">
      <h2 className="mb-1 font-bold">{t("patientDetail.labTrend.title")}</h2>
      <p className="mb-3 text-xs text-muted">{t("patientDetail.labTrend.subtitle")}</p>
      {isLoading ? (
        <p className="text-sm text-muted">{t("patientDetail.labTrend.loading")}</p>
      ) : tests.length === 0 ? (
        <p className="text-sm text-muted">{t("patientDetail.labTrend.empty")}</p>
      ) : (
        <ul className="space-y-3">
          {tests.map((test) => {
            const latest = test.entries[0];
            return (
              <li key={test.test_name} className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold">{test.test_name}</div>
                  <div className="text-xs text-muted">
                    {new Date(latest.taken_at).toLocaleDateString()} · {test.entries.length}{" "}
                    {t("patientDetail.labTrend.readings")}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Sparkline entries={test.entries} />
                  <span
                    className={`text-sm font-semibold ${
                      latest.is_critical ? "text-danger" : latest.is_abnormal ? "text-warning" : ""
                    }`}
                  >
                    {latest.value}
                    {test.unit ? ` ${test.unit}` : ""}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
