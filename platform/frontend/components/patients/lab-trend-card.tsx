"use client";

import { useQuery } from "@tanstack/react-query";
import { api, type LabHistoryEntry } from "@/lib/api";
import { friendlyTestName } from "@/lib/clinical-text";
import { useLanguage } from "@/lib/language";
import MiniTrend from "@/components/dashboard/mini-trend";

/** `entries` arrives newest-first (how a clinician reads the list), so the
 * line is drawn from the reversed copy. */
function Sparkline({ entries }: { entries: LabHistoryEntry[] }) {
  const chronological = [...entries].reverse();
  const last = chronological[chronological.length - 1];
  return (
    <MiniTrend
      values={chronological.map((e) => e.value)}
      lastTone={last?.is_critical ? "danger" : last?.is_abnormal ? "warning" : "neutral"}
      label={`Trend: ${chronological.map((e) => e.value).join(" → ")}`}
    />
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
                  <div className="truncate text-sm font-semibold">{friendlyTestName(test.test_name, t)}</div>
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
