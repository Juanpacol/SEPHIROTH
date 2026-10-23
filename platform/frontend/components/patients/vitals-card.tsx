"use client";

/** The patient's latest recorded vital signs, each against its normal range: the number in the display
 * face, tinted when it is outside, with when it was taken. Vitals are recorded at visits, so a reading's
 * date always shows; nothing is drawn for a vital that was never recorded. */
import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { api, type VitalSpecOut } from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { relativeTime } from "@/lib/relative-time";

/** The vitals worth a glance, in reading order; weight and height have no "normal" and are left to the visit. */
const SHOWN = [
  "systolic",
  "diastolic",
  "heart_rate",
  "respiratory_rate",
  "temperature",
  "oxygen_saturation",
  "glucose",
];

function outside(spec: VitalSpecOut, value: number): "high" | "medium" | null {
  if (value >= spec.normal_low && value <= spec.normal_high) return null;
  const span = Math.max(spec.normal_high - spec.normal_low, 1e-6);
  const distance = value < spec.normal_low ? spec.normal_low - value : value - spec.normal_high;
  return distance > span * 0.5 ? "high" : "medium";
}

export default function VitalsCard({ patientId }: { patientId: string }) {
  const { t, lang } = useLanguage();
  const { data: last, isLoading } = useQuery({
    queryKey: ["patient-last-vitals", patientId],
    queryFn: () => api.lastVitals(patientId),
  });
  const { data: spec } = useQuery({
    queryKey: ["vitals-spec"],
    queryFn: api.vitalsSpec,
    staleTime: Infinity,
  });

  const readings = last?.readings ?? {};
  const rows = (spec?.vitals ?? [])
    .filter((v) => SHOWN.includes(v.key) && readings[v.key] !== undefined)
    .sort((a, b) => SHOWN.indexOf(a.key) - SHOWN.indexOf(b.key));
  const label = (v: VitalSpecOut) =>
    t(`dashboard.vital.${v.key}`) !== `dashboard.vital.${v.key}` ? t(`dashboard.vital.${v.key}`) : v.label;

  return (
    <div className="card" data-testid="vitals-card">
      <h2 className="eyebrow flex items-center gap-2 text-muted">
        <Activity size={13} className="text-primary-ink" /> {t("patientDetail.vitals.title")}
      </h2>
      {isLoading ? (
        <p className="mt-3 text-sm text-muted">{t("patientDetail.vitals.loading")}</p>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("patientDetail.vitals.empty")}</p>
      ) : (
        <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-4">
          {rows.map((v) => {
            const reading = readings[v.key];
            const flag = outside(v, reading.value);
            const tone = flag === "high" ? "text-danger" : flag === "medium" ? "text-warning" : "text-ink";
            return (
              <li key={v.key} className="min-w-0">
                <div className="eyebrow truncate text-muted">{label(v)}</div>
                <div className="mt-1 flex items-baseline gap-1.5">
                  <span className={`font-display text-3xl font-light leading-none ${tone}`}>
                    {reading.value.toFixed(v.decimals)}
                  </span>
                  <span className="text-[11px] text-muted">{v.unit}</span>
                </div>
                <div className="mt-0.5 text-[11px] text-muted">
                  {relativeTime(reading.at, lang)} · {v.normal_low}–{v.normal_high}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
