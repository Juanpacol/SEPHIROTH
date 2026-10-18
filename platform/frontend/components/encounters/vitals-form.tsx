"use client";

/** Vitals, entered the way they are measured.
 *
 * Blood pressure is one field, not two. A clinician reads "210 over 120" and
 * writes it as one thing; a form with two boxes for it is a form that gets one
 * box filled, and a lone systolic is a reading nobody can act on.
 *
 * The ranges come from `GET /api/encounters/vitals/spec` rather than being
 * restated here. A range the UI validates against and a range the API enforces
 * have to be the same range, and two copies of a clinical bound drift.
 *
 * Two different things come from the patient's history, and they are kept
 * apart on purpose. The autofill button copies weight and height, which do not
 * change between visits. Under every field, `lastReadings` shows the previous
 * reading as plain text: a reference, never a value that can be copied, because
 * every other vital is a measurement of the moment.
 */

import { useEffect, useId, useMemo, useState } from "react";

import { type Encounter, type LastVitalReading, type VitalSpecOut } from "@/lib/api";
import { type Lang, useLanguage } from "@/lib/language";

export interface VitalsAutofill {
  /** Pressed → the page writes weight/height into the empty fields and saves. */
  onApply: () => void;
  /** loading: history in flight · none: no earlier weight or height ·
   * filled: both fields already have a value · ready: there is something to fill. */
  status: "loading" | "none" | "filled" | "ready";
}

interface Props {
  vitals: Record<string, number>;
  specs: VitalSpecOut[];
  findings: Encounter["vital_findings"];
  disabled?: boolean;
  onChange: (vitals: Record<string, number | "">) => void;
  autofill?: VitalsAutofill;
  /** Latest earlier reading per vital. Omit it (not editable, or still
   * loading) and no reference is shown; pass `{}` for "no history at all". */
  lastReadings?: Record<string, LastVitalReading>;
}

/** Rendered as one field even though it is stored as two columns. */
const BP_KEYS = ["systolic", "diastolic"] as const;

function parseBloodPressure(text: string): { systolic: number; diastolic: number } | null {
  const [left, right] = text.split("/");
  if (right === undefined) return null;
  const systolic = Number(left.trim());
  const diastolic = Number(right.trim());
  if (!Number.isFinite(systolic) || !Number.isFinite(diastolic)) return null;
  return { systolic, diastolic };
}

const AUTOFILL_STATUS_KEY = {
  loading: "encounter.vitals.autofillLoading",
  none: "encounter.vitals.autofillEmpty",
  filled: "encounter.vitals.autofillDone",
  ready: "encounter.vitals.autofillHint",
} as const;

const HAS_ZONE = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;

/** Backend datetimes are naive UTC, so a zone-less string gets `Z` appended
 * (same convention as `lib/relative-time.ts`). */
function visitDate(iso: string, lang: Lang): string {
  const date = new Date(HAS_ZONE.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(lang, { day: "numeric", month: "short", year: "numeric" });
}

function formatReading(spec: VitalSpecOut, value: number): string {
  return `${value.toFixed(spec.decimals)}${spec.unit ? ` ${spec.unit}` : ""}`;
}

export default function VitalsForm({ vitals, specs, findings, disabled, onChange, autofill, lastReadings }: Props) {
  const { t, lang } = useLanguage();
  const [bp, setBp] = useState("");
  const uid = useId();

  /** "Last: 70.0 kg · 1 Oct 2026", or the no-history line; null when no reference applies. */
  function lastReadingText(key: string): string | null {
    if (lastReadings === undefined) return null;
    const reading = lastReadings[key];
    if (!reading) return t("encounter.vitals.noLastReading");
    const spec = specs.find((s) => s.key === key);
    if (!spec) return null;
    return t("encounter.vitals.lastReading")
      .replace("{value}", formatReading(spec, reading.value))
      .replace("{date}", visitDate(reading.at, lang));
  }

  /** Blood pressure is one reading: shown only when both halves came from the
   * same visit (the API guarantees it; this is the second lock). */
  function lastBloodPressureText(): string | null {
    if (lastReadings === undefined) return null;
    const systolic = lastReadings.systolic;
    const diastolic = lastReadings.diastolic;
    if (!systolic || !diastolic || systolic.encounter_id !== diastolic.encounter_id) {
      return t("encounter.vitals.noLastReading");
    }
    return t("encounter.vitals.lastReading")
      .replace("{value}", `${systolic.value}/${diastolic.value} mmHg`)
      .replace("{date}", visitDate(systolic.at, lang));
  }

  useEffect(() => {
    const { systolic, diastolic } = vitals;
    setBp(systolic != null && diastolic != null ? `${systolic}/${diastolic}` : "");
  }, [vitals]);

  const flagged = useMemo(
    () => new Map(findings.map((finding) => [finding.key, finding])),
    [findings],
  );
  const others = useMemo(
    () => specs.filter((spec) => !BP_KEYS.includes(spec.key as (typeof BP_KEYS)[number])),
    [specs],
  );

  function commitBloodPressure(text: string) {
    const parsed = parseBloodPressure(text);
    // An unparseable entry clears both halves rather than keeping a stale one:
    // a systolic left over from a previous reading is worse than a blank.
    onChange({ systolic: parsed?.systolic ?? "", diastolic: parsed?.diastolic ?? "" });
  }

  const bpFinding = flagged.get("systolic") ?? flagged.get("diastolic");
  const bpReference = lastBloodPressureText();
  const showAutofill =
    autofill !== undefined &&
    !disabled &&
    specs.some((s) => s.key === "weight" || s.key === "height");

  return (
    <div className="flex flex-col gap-3">
      {showAutofill && autofill ? (
        <div className="flex flex-col gap-1">
          <button
            type="button"
            onClick={autofill.onApply}
            disabled={disabled || autofill.status !== "ready"}
            className="btn-secondary tap self-start"
          >
            {t("encounter.vitals.autofill")}
          </button>
          <span className="text-xs text-muted">{t(AUTOFILL_STATUS_KEY[autofill.status])}</span>
          <span className="text-xs text-muted">{t("encounter.vitals.autofillNote")}</span>
        </div>
      ) : null}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
          <span className="text-xs font-medium text-ink/70">{t("encounter.vitals.bp")}</span>
          <input
            type="text"
            inputMode="numeric"
            placeholder="120/80"
            aria-label={t("encounter.vitals.bp")}
            aria-describedby={bpReference !== null ? `${uid}-bp-last` : undefined}
            value={bp}
            disabled={disabled}
            onChange={(event) => setBp(event.target.value)}
            onBlur={(event) => commitBloodPressure(event.target.value)}
            className={`tap rounded-lg border px-3 py-2 text-sm ${
              bpFinding ? "border-danger bg-danger/5" : "border-line bg-card"
            } disabled:opacity-60`}
            aria-invalid={bpFinding ? true : undefined}
          />
          {bpFinding ? (
            <span className="text-xs text-danger">{bpFinding.detail}</span>
          ) : (
            <span className="text-xs text-ink/40">mmHg</span>
          )}
          {bpReference !== null ? (
            <span id={`${uid}-bp-last`} className="text-xs text-muted">
              {bpReference}
            </span>
          ) : null}
        </label>

        {others.map((spec) => {
          const finding = flagged.get(spec.key);
          const value = vitals[spec.key];
          const reference = lastReadingText(spec.key);
          return (
            <label key={spec.key} className="flex flex-col gap-1">
              <span className="text-xs font-medium text-ink/70">{spec.label}</span>
              <input
                type="number"
                inputMode="decimal"
                step={spec.decimals > 0 ? 0.1 : 1}
                min={spec.min}
                max={spec.max}
                value={value ?? ""}
                disabled={disabled}
                // Named explicitly: the wrapping label also holds the unit hint,
                // and a screen reader announcing "Frecuencia cardíaca 60 a 100"
                // as the field's name buries the name in the hint.
                aria-label={spec.label}
                aria-describedby={reference !== null ? `${uid}-${spec.key}-last` : undefined}
                onChange={(event) =>
                  onChange({
                    [spec.key]: event.target.value === "" ? "" : Number(event.target.value),
                  })
                }
                className={`tap rounded-lg border px-3 py-2 text-sm ${
                  finding ? "border-danger bg-danger/5" : "border-line bg-card"
                } disabled:opacity-60`}
                aria-invalid={finding ? true : undefined}
              />
              {finding ? (
                <span className="text-xs text-danger">{finding.detail}</span>
              ) : (
                <span className="text-xs text-ink/40">
                  {spec.unit || `${spec.normal_low}–${spec.normal_high}`}
                </span>
              )}
              {reference !== null ? (
                <span id={`${uid}-${spec.key}-last`} className="text-xs text-muted">
                  {reference}
                </span>
              ) : null}
            </label>
          );
        })}
      </div>
    </div>
  );
}
