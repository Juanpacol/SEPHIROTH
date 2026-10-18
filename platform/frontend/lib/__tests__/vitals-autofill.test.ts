import { describe, expect, it } from "vitest";
import { AUTOFILL_VITAL_KEYS, autofillPlan, type Readings } from "@/lib/vitals-autofill";

const reading = (value: number, at = "2026-06-01T09:00:00") => ({ value, at, encounter_id: `e-${value}` });

describe("autofillPlan", () => {
  it("only ever touches weight and height", () => {
    expect([...AUTOFILL_VITAL_KEYS]).toEqual(["weight", "height"]);
  });

  it("fills weight and height from their own latest readings", () => {
    const readings: Readings = { weight: reading(70, "2026-10-01T09:00:00"), height: reading(170, "2025-01-01T09:00:00") };

    expect(autofillPlan(readings, {})).toEqual({ values: { weight: 70, height: 170 }, hasHistory: true });
  });

  it("never copies a measurement of the moment, however recent", () => {
    const readings: Readings = {
      weight: reading(70),
      systolic: reading(120),
      diastolic: reading(80),
      heart_rate: reading(64),
      respiratory_rate: reading(16),
      temperature: reading(36.6),
      oxygen_saturation: reading(98),
      glucose: reading(95),
      pain_score: reading(2),
    };

    expect(Object.keys(autofillPlan(readings, {}).values)).toEqual(["weight"]);
  });

  it("never replaces a value that is already there", () => {
    const readings: Readings = { weight: reading(70), height: reading(170) };

    expect(autofillPlan(readings, { weight: 82 })).toEqual({ values: { height: 170 }, hasHistory: true });
  });

  it("has nothing to write once both fields are filled, but still knows there is history", () => {
    const readings: Readings = { weight: reading(70), height: reading(170) };

    expect(autofillPlan(readings, { weight: 70, height: 170 })).toEqual({ values: {}, hasHistory: true });
  });

  it("reports no history when no earlier visit recorded either", () => {
    expect(autofillPlan({}, {})).toEqual({ values: {}, hasHistory: false });
    expect(autofillPlan(undefined, {})).toEqual({ values: {}, hasHistory: false });
    // Other vitals alone are not weight/height history.
    expect(autofillPlan({ heart_rate: reading(64) }, {}).hasHistory).toBe(false);
  });

  it("ignores readings that are not finite positive numbers", () => {
    const readings = {
      weight: { ...reading(0) },
      height: { ...reading(-5) },
    } as Readings;

    expect(autofillPlan(readings, {})).toEqual({ values: {}, hasHistory: false });
    expect(autofillPlan({ weight: { ...reading(Number.NaN) } } as Readings, {}).hasHistory).toBe(false);
  });

  it("treats a missing current value, not a zero, as the empty field", () => {
    const readings: Readings = { weight: reading(70) };

    expect(autofillPlan(readings, { height: 170 }).values).toEqual({ weight: 70 });
  });
});
