/** Picks the source encounter for the vitals-autofill control.
 *
 * Pure and fetch-free so the clinical filter — signed only, weight/height
 * only, newest first, never the current encounter — is unit-testable without
 * rendering a page. See `components/encounters/vitals-form.tsx` for the
 * control this feeds. */

import { type Encounter } from "@/lib/api";

/** The only vital keys autofill may ever touch. */
export const AUTOFILL_VITAL_KEYS = ["weight", "height"] as const;

export interface PriorVitalsSource {
  encounterId: string;
  /** `started_at` of the source encounter, verbatim from the API. */
  startedAt: string;
  /** Only keys from AUTOFILL_VITAL_KEYS, only finite positive numbers. */
  vitals: Record<string, number>;
}

export function pickPriorVitals(
  items: Encounter[],
  options: { excludeEncounterId: string }
): PriorVitalsSource | null {
  const candidates: PriorVitalsSource[] = [];

  for (const item of items) {
    if (item.id === options.excludeEncounterId) continue;
    if (item.status !== "signed" && item.status !== "amended") continue;
    if (Number.isNaN(Date.parse(item.started_at))) continue;

    const vitals: Record<string, number> = {};
    for (const key of AUTOFILL_VITAL_KEYS) {
      const value = item.vitals[key];
      if (typeof value === "number" && Number.isFinite(value) && value > 0) {
        vitals[key] = value;
      }
    }
    if (Object.keys(vitals).length === 0) continue;

    candidates.push({ encounterId: item.id, startedAt: item.started_at, vitals });
  }

  if (candidates.length === 0) return null;

  candidates.sort((a, b) => Date.parse(b.startedAt) - Date.parse(a.startedAt));
  return candidates[0];
}
