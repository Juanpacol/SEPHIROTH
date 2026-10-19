import { describe, expect, it } from "vitest";
import { AUTOFILL_VITAL_KEYS, autofillPlan, autofillSummary, type Readings } from "@/lib/vitals-autofill";

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

describe("autofillSummary", () => {
  const readings: Readings = {
    weight: reading(70, "2026-10-01T09:00:00"),
    height: reading(170, "2025-01-01T09:00:00"),
  };

  it("lists what would be copied, each with the visit it comes from", () => {
    expect(autofillSummary(readings, {})).toEqual({
      copy: [
        { key: "weight", value: 70, at: "2026-10-01T09:00:00" },
        { key: "height", value: 170, at: "2025-01-01T09:00:00" },
      ],
      filled: [],
      missing: [],
    });
  });

  it("says which fields have no earlier value at all", () => {
    expect(autofillSummary({ weight: reading(70) }, {}).missing).toEqual(["height"]);
    expect(autofillSummary({}, {}).missing).toEqual(["weight", "height"]);
    expect(autofillSummary(undefined, {})).toEqual({ copy: [], filled: [], missing: ["weight", "height"] });
  });

  it("treats a value that is not a usable reading as missing", () => {
    const bad: Readings = { weight: reading(0), height: reading(Number.NaN) };

    expect(autofillSummary(bad, {}).missing).toEqual(["weight", "height"]);
  });

  it("names the visit only for filled values that match it, not for typed ones", () => {
    const summary = autofillSummary(readings, { weight: 70, height: 181 });

    expect(summary.filled).toEqual([
      { key: "weight", at: "2026-10-01T09:00:00" },
      { key: "height", at: null },
    ]);
    expect(summary.copy).toEqual([]);
  });

  it("filled with no earlier value is filled, with no visit, and not missing", () => {
    const summary = autofillSummary({}, { weight: 70 });

    expect(summary.filled).toEqual([{ key: "weight", at: null }]);
    expect(summary.missing).toEqual(["height"]);
  });

  it("agrees with autofillPlan about what is copyable", () => {
    const cases: Record<string, number>[] = [{}, { weight: 82 }, { weight: 82, height: 160 }];
    for (const current of cases) {
      const plan = autofillPlan(readings, current);
      const summary = autofillSummary(readings, current);

      expect(summary.copy.map((c) => c.key)).toEqual(Object.keys(plan.values));
    }
  });
});
