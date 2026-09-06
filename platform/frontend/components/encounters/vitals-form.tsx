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
 */

import { useEffect, useMemo, useState } from "react";

import { type Encounter, type VitalSpecOut } from "@/lib/api";
import { useLanguage } from "@/lib/language";

interface Props {
  vitals: Record<string, number>;
  specs: VitalSpecOut[];
  findings: Encounter["vital_findings"];
  disabled?: boolean;
  onChange: (vitals: Record<string, number | "">) => void;
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

export default function VitalsForm({ vitals, specs, findings, disabled, onChange }: Props) {
  const { t } = useLanguage();
  const [bp, setBp] = useState("");

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

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
        <span className="text-xs font-medium text-ink/70">{t("encounter.vitals.bp")}</span>
        <input
          type="text"
          inputMode="numeric"
          placeholder="120/80"
          aria-label={t("encounter.vitals.bp")}
          value={bp}
          disabled={disabled}
          onChange={(event) => setBp(event.target.value)}
          onBlur={(event) => commitBloodPressure(event.target.value)}
          className={`tap rounded-lg border px-3 py-2 text-sm ${
            bpFinding ? "border-danger bg-danger/5" : "border-border bg-white"
          } disabled:opacity-60`}
          aria-invalid={bpFinding ? true : undefined}
        />
        {bpFinding ? (
          <span className="text-xs text-danger">{bpFinding.detail}</span>
        ) : (
          <span className="text-xs text-ink/40">mmHg</span>
        )}
      </label>

      {others.map((spec) => {
        const finding = flagged.get(spec.key);
        const value = vitals[spec.key];
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
              onChange={(event) =>
                onChange({
                  [spec.key]: event.target.value === "" ? "" : Number(event.target.value),
                })
              }
              className={`tap rounded-lg border px-3 py-2 text-sm ${
                finding ? "border-danger bg-danger/5" : "border-border bg-white"
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
          </label>
        );
      })}
    </div>
  );
}
