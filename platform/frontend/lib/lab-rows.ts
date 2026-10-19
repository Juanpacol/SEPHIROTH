/** One row per lab test for the patient's lab card.
 *
 * Two sources describe the same patient: the lab history (`lab_results` table,
 * one row per reading, with a status and a reference range) and the snapshot
 * (`Patient.lab_results`, the latest value as plain text). A test in both is one
 * row, taken from the history. A test only in the snapshot is still shown, with
 * what it has: its value, and no date, status or trend, because none was
 * recorded and inventing them would be worse than a gap.
 *
 * Pure and fetch-free so the ordering and the status rules are testable
 * without rendering anything.
 */

import { type LabHistoryTest, type PatientLabHistory } from "@/lib/api";
import { normalizeTestKey } from "@/lib/clinical-text";

export type LabStatus = "critical" | "high" | "low" | "abnormal" | "normal" | "unknown";

export interface LabReading {
  value: number;
  takenAt: string;
}

export interface LabRow {
  /** Normalised test key: identifies the test across both sources. */
  key: string;
  /** The name as recorded, for `friendlyTestName`. */
  testName: string;
  /** The value as it is shown: a number, or the snapshot's own text. */
  value: string;
  unit: string;
  status: LabStatus;
  takenAt: string | null;
  low: number | null;
  high: number | null;
  /** Oldest first, ready to draw. */
  readings: LabReading[];
  hasHistory: boolean;
}

/** Blood pressure is a vital sign, not a lab: it belongs with the vitals. */
export function isBloodPressure(testName: string): boolean {
  const key = normalizeTestKey(testName);
  return key === "bp" || key.startsWith("bp_") || key.includes("systolic") || key.includes("diastolic");
}

const RANK: Record<LabStatus, number> = { critical: 0, high: 1, low: 1, abnormal: 1, normal: 2, unknown: 3 };

/** Why this value is flagged, in one word. A critical stays critical; an
 * abnormal one says which side of the range it is on when the range is known. */
export function labStatus(entry: {
  value: number;
  is_abnormal: boolean;
  is_critical: boolean;
  reference_low?: number | null;
  reference_high?: number | null;
}): LabStatus {
  if (entry.is_critical) return "critical";
  if (!entry.is_abnormal) return "normal";
  const { value, reference_low: low, reference_high: high } = entry;
  if (low != null && value < low) return "low";
  if (high != null && value > high) return "high";
  return "abnormal";
}

/** `"6.8%"` → 6.8 and `"%"`; `"102 mg/dL"` → 102 and `"mg/dL"`. Anything that is
 * not a plain number with an optional unit (`"138/86"`, `"pending"`) comes back
 * as its own text with no unit. */
export function parseSnapshotValue(raw: string): { value: string; unit: string } {
  const text = String(raw ?? "").trim();
  const match = /^(-?\d+(?:[.,]\d+)?)\s*(.*)$/.exec(text);
  if (!match || match[2].startsWith("/")) return { value: text, unit: "" };
  return { value: match[1].replace(",", "."), unit: match[2].trim() };
}

function fromHistory(test: LabHistoryTest): LabRow {
  const latest = test.entries[0];
  return {
    key: normalizeTestKey(test.test_name),
    testName: test.test_name,
    value: String(latest.value),
    unit: test.unit,
    status: labStatus(latest),
    takenAt: latest.taken_at,
    low: latest.reference_low ?? null,
    high: latest.reference_high ?? null,
    readings: test.entries.map((e) => ({ value: e.value, takenAt: e.taken_at })).reverse(),
    hasHistory: true,
  };
}

export function buildLabRows(
  history: PatientLabHistory | undefined,
  snapshot: Record<string, string> | undefined,
  displayName: (testName: string) => string,
): LabRow[] {
  const rows = new Map<string, LabRow>();

  for (const test of history?.tests ?? []) {
    if (test.entries.length === 0 || isBloodPressure(test.test_name)) continue;
    const row = fromHistory(test);
    if (!rows.has(row.key)) rows.set(row.key, row);
  }

  for (const [name, raw] of Object.entries(snapshot ?? {})) {
    const key = normalizeTestKey(name);
    if (isBloodPressure(name) || rows.has(key)) continue;
    const { value, unit } = parseSnapshotValue(raw);
    rows.set(key, {
      key,
      testName: name,
      value,
      unit,
      status: "unknown",
      takenAt: null,
      low: null,
      high: null,
      readings: [],
      hasHistory: false,
    });
  }

  return Array.from(rows.values()).sort(
    (a, b) => RANK[a.status] - RANK[b.status] || displayName(a.testName).localeCompare(displayName(b.testName)),
  );
}
