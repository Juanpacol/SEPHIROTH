/** What the vitals-autofill control may write.
 *
 * Pure and fetch-free so the clinical rule is unit-testable without rendering a
 * page: only weight and height, only into fields still empty, each from its own
 * latest reading. Which reading is the latest is the server's call
 * (`GET /api/encounters/last-vitals`); see `components/encounters/vitals-form.tsx`
 * for the control this feeds.
 *
 * Every other vital is a measurement of the moment. Copying one forward would
 * put a number in the chart that nobody took at this visit, so none of them is
 * ever written from here -- they are only *shown* as a reference.
 */

import { type LastVitalReading } from "@/lib/api";

/** The only vital keys autofill may ever touch. */
export const AUTOFILL_VITAL_KEYS = ["weight", "height"] as const;

export type Readings = Record<string, LastVitalReading>;

export interface AutofillPlan {
  /** Weight/height to write: only empty fields, only valid positive numbers. */
  values: Record<string, number>;
  /** Whether any earlier visit recorded a weight or a height at all. */
  hasHistory: boolean;
}

export function autofillPlan(readings: Readings | undefined, current: Record<string, number>): AutofillPlan {
  const values: Record<string, number> = {};
  let hasHistory = false;

  for (const key of AUTOFILL_VITAL_KEYS) {
    const value = readings?.[key]?.value;
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) continue;
    hasHistory = true;

    const present = current[key];
    const isEmpty = typeof present !== "number" || !Number.isFinite(present);
    if (isEmpty) values[key] = value;
  }

  return { values, hasHistory };
}
