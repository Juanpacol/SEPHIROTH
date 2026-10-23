"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  Activity,
  CalendarClock,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Pill,
  ShieldCheck,
  Siren,
  Users,
} from "lucide-react";
import type {
  DashboardAI,
  DashboardAlerts,
  DashboardEvolution,
  DashboardMedications,
  DashboardVitals,
  TodayAgenda,
} from "@/lib/api";
import { useLanguage } from "@/lib/language";
import { relativeTime } from "@/lib/relative-time";
import { slotTime } from "@/components/schedule/time";

/** True one frame after mount, so marks can draw themselves from zero. Instant under reduced motion (globals.css). */
function useGrown(): boolean {
  const [grown, setGrown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setGrown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return grown;
}

/** A count that may be missing from a partial payload reads as zero, never NaN. */
const n = (value: number | null | undefined): number => (Number.isFinite(value) ? (value as number) : 0);

const EASE = "ease-[cubic-bezier(0.22,1,0.36,1)]";

function PanelTitle({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <h2 className="eyebrow flex items-center gap-2 text-muted">
      {icon} {children}
    </h2>
  );
}

interface RingSegment {
  value: number;
  className: string;
}

/** A ring of arcs that sweep in one after another. Arcs have round caps and a small gap, so neighbours never touch. */
function Ring({
  segments,
  total,
  size = 132,
  thickness = 11,
  label,
  children,
}: {
  segments: RingSegment[];
  total: number;
  size?: number;
  thickness?: number;
  label: string;
  children?: ReactNode;
}) {
  const grown = useGrown();
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const gap = segments.filter((s) => s.value > 0).length > 1 ? thickness * 0.55 : 0;
  let offset = 0;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={label}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={thickness}
          className="stroke-line/40"
        />
        {total > 0 &&
          segments.map((s, i) => {
            if (s.value <= 0) return null;
            const len = Math.max(0.5, (s.value / total) * c - gap);
            const start = offset;
            offset += (s.value / total) * c;
            return (
              <circle
                key={i}
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                strokeWidth={thickness}
                strokeLinecap="round"
                strokeDasharray={`${grown ? len : 0} ${c}`}
                strokeDashoffset={-(start + gap / 2)}
                className={`${s.className} transition-[stroke-dasharray] duration-[1100ms] ${EASE}`}
                style={{ transitionDelay: `${i * 140}ms` }}
              />
            );
          })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children}</div>
    </div>
  );
}

/** Four numbers a clinician reads first, in one slim panel. Colour only where the state is clinical. */
export function KpiStrip({
  critical,
  worsening,
  unreviewed,
  vitals,
}: {
  critical: number;
  worsening: number;
  unreviewed: number;
  vitals: number;
}) {
  const { t } = useLanguage();
  const items = [
    {
      key: "critical",
      value: critical,
      tone: critical > 0 ? "text-danger" : "text-ink",
    },
    {
      key: "worsening",
      value: worsening,
      tone: worsening > 0 ? "text-warning" : "text-ink",
    },
    {
      key: "unreviewed",
      value: unreviewed,
      tone: unreviewed > 0 ? "text-warning" : "text-ink",
    },
    {
      key: "vitals",
      value: vitals,
      tone: vitals > 0 ? "text-danger" : "text-ink",
    },
  ];
  return (
    <dl
      className="dash-panel grid grid-cols-2 gap-y-3 !py-3 sm:grid-cols-4 sm:divide-x sm:divide-line/60"
      data-testid="kpi-strip"
    >
      {items.map((item, i) => (
        <div key={item.key} className={`min-w-0 ${i % 2 === 1 ? "pl-4" : ""} ${i > 0 ? "sm:pl-6" : ""}`}>
          <dt className="eyebrow truncate text-muted">{t(`dashboard.kpi.${item.key}`)}</dt>
          <dd className={`mt-1 font-display text-4xl font-light leading-none ${item.tone}`}>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Patients by risk state as a ring, the total in the middle. State is named and iconed, never colour alone. */
export function RiskDonut({
  critical,
  moderate,
  stable,
}: {
  critical: number;
  moderate: number;
  stable: number;
}) {
  const { t } = useLanguage();
  const total = critical + moderate + stable;
  const rows = [
    {
      key: "critical",
      count: critical,
      ring: "stroke-danger",
      icon: AlertTriangle,
      tone: "text-danger",
    },
    {
      key: "moderate",
      count: moderate,
      ring: "stroke-warning",
      icon: AlertCircle,
      tone: "text-warning",
    },
    {
      key: "stable",
      count: stable,
      ring: "stroke-success",
      icon: CheckCircle2,
      tone: "text-success",
    },
  ];
  const summary = rows.map((r) => `${t(`dashboard.stat.${r.key}`)} ${r.count}`).join(", ");
  return (
    <div className="dash-panel h-full" data-testid="risk-donut">
      <div className="eyebrow text-muted">{t("dashboard.distribution.title")}</div>
      {total === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("dashboard.distribution.empty")}</p>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3">
          <Ring
            size={108}
            thickness={10}
            segments={rows.map((r) => ({ value: r.count, className: r.ring }))}
            total={total}
            label={summary}
          >
            <span className="font-display text-5xl font-light leading-none text-ink">{total}</span>
            <span className="eyebrow mt-1 text-muted">{t("dashboard.donut.patients")}</span>
          </Ring>
          <ul className="min-w-0 flex-1 space-y-2">
            {rows.map((r) => {
              const Icon = r.icon;
              return (
                <li key={r.key} className="flex items-center gap-2 text-sm">
                  <Icon size={14} className={`shrink-0 ${r.tone}`} aria-hidden />
                  <span className="min-w-0 flex-1 truncate text-muted">{t(`dashboard.stat.${r.key}`)}</span>
                  <span className="font-bold text-ink">{r.count}</span>
                  <span className="w-8 text-right text-[11px] text-muted">
                    {Math.round((r.count / total) * 100)}%
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Who is changing: worsening grows to the left of a centre line, improving to the right, the unchanged is a number. */
export function EvolutionBar({ data }: { data: DashboardEvolution }) {
  const { t } = useLanguage();
  const grown = useGrown();
  const worse = n(data.deteriorating_count);
  const better = n(data.improving_count);
  const same = n(data.no_change_count);
  const max = Math.max(1, worse, better);
  const summary = `${t("dashboard.evolution.worse")} ${worse}, ${t("dashboard.evolution.same")} ${same}, ${t("dashboard.evolution.better")} ${better}`;
  const half = (count: number, side: "l" | "r", bar: string) => (
    <div className={`flex h-6 items-center ${side === "l" ? "justify-end" : "justify-start"}`}>
      <div
        className={`${bar} h-3 rounded-full ${side === "l" ? "origin-right" : "origin-left"} transition-transform duration-[1000ms] ${EASE} ${grown ? "scale-x-100" : "scale-x-0"}`}
        style={{
          width: `${(count / max) * 100}%`,
          minWidth: count > 0 ? "10px" : 0,
        }}
      />
    </div>
  );
  return (
    <div className="dash-panel h-full" data-testid="evolution-bar">
      <PanelTitle icon={<Users size={13} className="text-primary-ink" />}>
        {t("dashboard.evolution.title")}
      </PanelTitle>
      {worse + better + same === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("dashboard.evolution.empty")}</p>
      ) : (
        <div className="mt-3" role="img" aria-label={summary}>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-3">
            <div className="text-right">
              <span className="font-display text-4xl font-light leading-none text-danger">{worse}</span>
              <span className="eyebrow ml-2 text-muted">{t("dashboard.evolution.worse")}</span>
            </div>
            <div className="eyebrow rounded-full bg-line/30 px-2 py-0.5 text-muted">
              {same} · {t("dashboard.evolution.same")}
            </div>
            <div>
              <span className="eyebrow mr-2 text-muted">{t("dashboard.evolution.better")}</span>
              <span className="font-display text-4xl font-light leading-none text-success">{better}</span>
            </div>
          </div>
          <div className="relative mt-2 grid grid-cols-2">
            <div className="absolute inset-y-0 left-1/2 w-px bg-line/70" aria-hidden />
            <div className="pr-1.5">{half(worse, "l", "bg-danger")}</div>
            <div className="pl-1.5">{half(better, "r", "bg-success")}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function reviewTime(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return null;
  if (seconds < 90) return `${Math.round(seconds)} s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

/** Alert review: the ring is the share already closed, the middle is how long review takes, the rest are counts. */
export function AlertRing({ data }: { data: DashboardAlerts }) {
  const { t } = useLanguage();
  const open = n(data.pending_review_count);
  const done = n(data.resolved_count);
  const avg = reviewTime(data.avg_review_seconds);
  const rows = [
    { key: "new", count: n(data.new_count), tone: "text-ink" },
    {
      key: "pending",
      count: open,
      tone: open > 0 ? "text-warning" : "text-ink",
    },
    { key: "resolved", count: done, tone: "text-success" },
  ];
  return (
    <div className="dash-panel h-full" data-testid="alert-ring">
      <PanelTitle icon={<Siren size={13} className="text-primary-ink" />}>
        {t("dashboard.alerts.title")}
      </PanelTitle>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Ring
          size={112}
          thickness={10}
          total={open + done}
          segments={[
            { value: done, className: "stroke-success" },
            { value: open, className: "stroke-warning" },
          ]}
          label={`${t("dashboard.alerts.resolved")} ${done}, ${t("dashboard.alerts.pending")} ${open}`}
        >
          <span className="font-display text-3xl font-light leading-none text-ink">{avg ?? "—"}</span>
          <span className="mt-1 max-w-[5.5rem] text-[10px] leading-tight text-muted">
            {t("dashboard.alerts.avgReview")}
          </span>
        </Ring>
        <ul className="min-w-0 flex-1 space-y-2">
          {rows.map((r) => (
            <li key={r.key} className="flex items-baseline gap-2 text-sm">
              <span className="min-w-0 flex-1 truncate text-muted">{t(`dashboard.alerts.${r.key}`)}</span>
              <span className={`font-display text-2xl font-light leading-none ${r.tone}`}>{r.count}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/** Medication safety signals, largest first. Round-ended bars in one hue, so length is the only thing to compare. */
export function MedicationBars({ data }: { data: DashboardMedications }) {
  const { t } = useLanguage();
  const grown = useGrown();
  const rows = [
    { key: "interaction", count: n(data.interaction_count) },
    { key: "contraindication", count: n(data.contraindication_count) },
    { key: "highRisk", count: n(data.high_risk_medication_count) },
    { key: "doseAnomaly", count: n(data.dose_anomaly_count) },
    { key: "polypharmacy", count: n(data.polypharmacy_patient_count) },
  ].sort((a, b) => b.count - a.count);
  const max = Math.max(1, ...rows.map((r) => r.count));
  const none = rows.every((r) => r.count === 0);
  return (
    <div className="dash-panel h-full" data-testid="medication-bars">
      <PanelTitle icon={<Pill size={13} className="text-primary-ink" />}>
        {t("dashboard.meds.title")}
      </PanelTitle>
      {none ? (
        <p className="mt-3 text-sm text-muted">{t("dashboard.meds.none")}</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {rows.map((r, i) => (
            <li
              key={r.key}
              className="grid grid-cols-[minmax(7.5rem,1.2fr)_minmax(0,1fr)_1.25rem] items-center gap-x-3 text-[13px]"
            >
              <span className="truncate text-muted">{t(`dashboard.meds.${r.key}`)}</span>
              <div className="h-1.5 w-full rounded-full bg-line/40" aria-hidden>
                <div
                  className={`h-full origin-left rounded-full bg-primary-ink transition-transform duration-[1000ms] ${EASE} ${grown ? "scale-x-100" : "scale-x-0"}`}
                  style={{
                    width: `${(r.count / max) * 100}%`,
                    minWidth: r.count > 0 ? "8px" : 0,
                    transitionDelay: `${i * 90}ms`,
                  }}
                />
              </div>
              <span className="text-right font-bold text-ink">{r.count}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Answer quality: the ring is the share of answers clinicians rated useful (only once there are enough ratings
 * for a percentage to mean anything); the four criteria are 1–5 pips. */
const MIN_RATINGS_FOR_PERCENT = 3;

export function QualityRing({ data }: { data: DashboardAI }) {
  const { t } = useLanguage();
  const enough = data.helpful_ratio !== null && data.ratings_count >= MIN_RATINGS_FOR_PERCENT;
  const pct = enough ? Math.round((data.helpful_ratio as number) * 100) : null;
  const criteria = (["grounding", "completeness", "safety", "abstention"] as const).filter(
    (c) => data.auto_grade_averages[c] !== undefined
  );
  const ratings =
    data.ratings_count === 1
      ? t("dashboard.quality.oneRating")
      : t("dashboard.quality.ratings").replace("{count}", String(data.ratings_count));
  return (
    <div className="dash-panel h-full" data-testid="answer-quality">
      <PanelTitle icon={<ShieldCheck size={13} className="text-primary-ink" />}>
        {t("dashboard.quality.title")}
      </PanelTitle>
      {data.helpful_ratio === null && criteria.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("dashboard.quality.none")}</p>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-3">
          {pct !== null && (
            <Ring
              size={104}
              thickness={10}
              total={100}
              segments={[{ value: pct, className: "stroke-primary-ink" }]}
              label={`${pct}% ${t("dashboard.quality.helpful")}`}
            >
              <span className="font-display text-4xl font-light leading-none text-ink">{pct}%</span>
              <span className="mt-1 text-[10px] text-muted">{t("dashboard.quality.helpful")}</span>
            </Ring>
          )}
          <div className="min-w-0 flex-1 space-y-1.5" data-testid="auto-grades">
            <p className="text-xs text-muted">
              {ratings}
              {" · "}
              <span className={data.pending_review_count > 0 ? "font-semibold text-warning" : ""}>
                {t("dashboard.quality.pending").replace("{count}", String(data.pending_review_count))}
              </span>
            </p>
            {pct === null && data.helpful_ratio !== null && (
              <p className="text-[11px] text-muted">{t("dashboard.quality.tooFew")}</p>
            )}
            {criteria.map((c) => {
              const value = data.auto_grade_averages[c] ?? 0;
              return (
                <div key={c} className="flex items-center gap-2 text-xs">
                  <span className="w-20 shrink-0 truncate text-muted">
                    {t(`dashboard.quality.criterion.${c}`)}
                  </span>
                  <span className="flex gap-0.5" aria-hidden>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <span
                        key={n}
                        className={`h-1.5 w-3 rounded-full ${value >= n - 0.5 ? "bg-primary-ink" : "bg-line/50"}`}
                      />
                    ))}
                  </span>
                  <span className="shrink-0 font-bold text-ink">{value.toFixed(1)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const fmtNumber = (value: number) => String(Math.round(value * 10) / 10);

/** Where a reading sits against its normal range: the range is a soft band, the reading a dot that slides in. */
function VitalRange({ value, low, high, tone }: { value: number; low: number; high: number; tone: string }) {
  const grown = useGrown();
  const span = high - low || 1;
  const min = Math.max(0, Math.min(low, value) - span * 0.35);
  const max = Math.max(high, value) + span * 0.35;
  const pos = (v: number) => `${(((v - min) / (max - min)) * 100).toFixed(1)}%`;
  return (
    <div className="relative h-1.5 w-full rounded-full bg-line/50" aria-hidden>
      <div
        className="absolute inset-y-0 rounded-full bg-success/30"
        style={{
          left: pos(low),
          width: `${(((high - low) / (max - min)) * 100).toFixed(1)}%`,
        }}
      />
      <div
        className={`absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-card transition-[left] duration-[900ms] ${EASE} ${tone}`}
        style={{ left: grown ? pos(value) : "0%" }}
      />
    </div>
  );
}

/** Why a patient needs attention, in what was measured: the vital that is out of range, against its normal
 * range and the reading before. Vitals are taken at visits, so every patient carries when it was measured. */
export function VitalsWatch({ data }: { data: DashboardVitals }) {
  const { t, lang } = useLanguage();
  const label = (key: string, fallback: string) =>
    t(`dashboard.vital.${key}`) !== `dashboard.vital.${key}` ? t(`dashboard.vital.${key}`) : fallback;
  return (
    <div className="dash-panel h-full" data-testid="vitals-watch">
      <div className="flex items-start justify-between gap-3">
        <PanelTitle icon={<Activity size={13} className="text-danger" />}>
          {t("dashboard.vitals.title")}
        </PanelTitle>
        {data.abnormal_patient_count > 0 && (
          <span className="font-display text-3xl font-light leading-none text-danger">
            {data.abnormal_patient_count}
          </span>
        )}
      </div>
      {data.patients.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("dashboard.vitals.empty")}</p>
      ) : (
        <ul className="mt-2 max-h-[17.5rem] divide-y divide-line/60 overflow-y-auto">
          {data.patients.map((p) => (
            <li key={p.patient_id} className="py-2">
              <div className="flex items-baseline justify-between gap-2">
                <Link
                  href={`/patients/${p.patient_id}`}
                  className="min-w-0 truncate text-sm font-semibold hover:text-primary"
                >
                  {p.patient_name}
                </Link>
                <span className="shrink-0 text-[11px] text-muted">
                  {t("dashboard.vitals.measured").replace("{when}", relativeTime(p.measured_at, lang))}
                </span>
              </div>
              <ul className="mt-1 space-y-1.5">
                {p.findings.slice(0, 3).map((f) => {
                  const high = f.severity === "high";
                  return (
                    <li
                      key={f.key}
                      className="grid grid-cols-[minmax(0,1fr)_5.5rem] items-center gap-x-4 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]"
                    >
                      <div className="min-w-0">
                        <div className="flex items-baseline gap-2">
                          <span
                            className={`font-display text-xl font-light leading-none ${high ? "text-danger" : "text-warning"}`}
                          >
                            {fmtNumber(f.value)}
                          </span>
                          <span className="text-[11px] text-muted">{f.unit}</span>
                          <span className="min-w-0 truncate text-xs text-muted">{label(f.key, f.label)}</span>
                        </div>
                        <div className="mt-0.5 text-[11px] text-muted">
                          {t("dashboard.vitals.normal")
                            .replace("{low}", fmtNumber(f.low))
                            .replace("{high}", fmtNumber(f.high))}
                          {f.previous &&
                            ` · ${t("dashboard.vitals.previous").replace("{value}", fmtNumber(f.previous.value))}`}
                        </div>
                      </div>
                      <VitalRange
                        value={f.value}
                        low={f.low}
                        high={f.high}
                        tone={high ? "bg-danger" : "bg-warning"}
                      />
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** What is booked today, in order, on a thin timeline; the next appointment is the one lit. */
export function AgendaPanel({ agenda }: { agenda: TodayAgenda }) {
  const { t } = useLanguage();
  return (
    <div className="dash-panel h-full" data-testid="agenda-panel">
      <div className="flex items-start justify-between gap-3">
        <PanelTitle icon={<CalendarClock size={13} className="text-primary-ink" />}>
          {t("dashboard.agenda.title")}
        </PanelTitle>
        {agenda.count > 0 && (
          <span className="font-display text-3xl font-light leading-none text-primary-ink">
            {agenda.count}
          </span>
        )}
      </div>
      {agenda.items.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{t("dashboard.agenda.empty")}</p>
      ) : (
        <ol className="relative mt-3 max-h-60 space-y-3 overflow-y-auto pl-4 before:absolute before:inset-y-1 before:left-[3px] before:w-px before:bg-line/70">
          {agenda.items.map((item) => {
            const next = item.start_at === agenda.next_at;
            return (
              <li key={item.id} className="relative min-w-0">
                <span
                  className={`absolute -left-4 top-1.5 h-[7px] w-[7px] rounded-full ${
                    next ? "bg-primary-ink ring-4 ring-primary-ink/20" : "bg-line"
                  }`}
                  aria-hidden
                />
                <div className="flex items-baseline gap-2">
                  <span
                    className={`font-display text-xl font-light leading-none ${next ? "text-primary-ink" : "text-ink"}`}
                  >
                    {slotTime(item.start_at)}
                  </span>
                  {next && <span className="eyebrow text-primary-ink">{t("dashboard.agenda.next")}</span>}
                </div>
                <div className="mt-0.5 truncate text-sm font-semibold">{item.patient_name}</div>
                <div className="truncate text-xs text-muted">{item.reason}</div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
