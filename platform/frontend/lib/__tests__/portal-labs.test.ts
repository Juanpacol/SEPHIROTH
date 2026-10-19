import { describe, expect, it } from "vitest";
import { type PortalLab } from "@/lib/api";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";
import { labExplanation, labRange, labValue } from "@/lib/portal-labs";

const lab = (over: Partial<PortalLab> = {}): PortalLab => ({
  share_id: "s-1",
  test_name: "potassium",
  value: 6.4,
  unit: "mmol/L",
  taken_at: "2026-10-10T08:00:00",
  reference_low: 3.5,
  reference_high: 5.1,
  standing: "inside",
  direction: null,
  message: "",
  shared_at: "2026-10-10T09:00:00",
  viewed_at: null,
  ...over,
});

const en = (key: string) => (EN as Record<string, string>)[key] ?? key;
const es = (key: string) => (ES as Record<string, string>)[key] ?? key;

describe("labExplanation", () => {
  it.each([
    [{ standing: "inside" }, "Your Potassium is within the usual range."],
    [{ standing: "outside", direction: "above" }, "Your Potassium is above the usual range."],
    [{ standing: "outside", direction: "below" }, "Your Potassium is below the usual range."],
    [{ standing: "outside", direction: null }, "Your Potassium is outside the usual range."],
    [
      { standing: "needs_attention", direction: "above" },
      "Your Potassium needs attention soon. Please follow your care team's instructions.",
    ],
    [{ standing: "unknown" }, "Your care team will go over this result with you."],
  ] as [Partial<PortalLab>, string][])("%j", (over, expected) => {
    expect(labExplanation(lab(over), en)).toBe(expected);
  });

  it("makes no judgement when it was never classified", () => {
    expect(labExplanation(lab({ standing: "unknown", reference_low: null, reference_high: null }), en)).not.toMatch(
      /range|above|below|attention/,
    );
  });

  it("says the same thing in Spanish", () => {
    expect(labExplanation(lab({ standing: "outside", direction: "below" }), es)).toBe(
      "Tu Potasio está por debajo del rango habitual.",
    );
  });

  it("has a sentence, in both languages, for every standing", () => {
    for (const standing of ["inside", "outside", "needs_attention", "unknown"] as const) {
      for (const t of [en, es]) {
        expect(labExplanation(lab({ standing }), t)).not.toContain("portal.labs.explain");
      }
    }
    for (const key of ["outside.above", "outside.below"]) {
      expect(EN[`portal.labs.explain.${key}` as keyof typeof EN]).toBeTruthy();
      expect(ES[`portal.labs.explain.${key}` as keyof typeof ES]).toBeTruthy();
    }
  });
});

describe("labRange and labValue", () => {
  it("formats both bounds, one bound, and none, with the unit kept to the number", () => {
    expect(labRange(lab())).toBe("3.5–5.1 mmol/L");
    expect(labRange(lab({ reference_low: null }))).toBe("≤ 5.1 mmol/L");
    expect(labRange(lab({ reference_high: null }))).toBe("≥ 3.5 mmol/L");
    expect(labRange(lab({ reference_low: null, reference_high: null }))).toBeNull();
  });

  it("omits an empty unit without a stray space", () => {
    expect(labRange(lab({ unit: "" }))).toBe("3.5–5.1");
    expect(labValue(lab({ unit: "" }))).toBe("6.4");
    expect(labValue(lab())).toBe("6.4 mmol/L");
  });
});
