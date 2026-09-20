import { describe, expect, it } from "vitest";
import { pickPriorVitals } from "@/lib/vitals-autofill";
import { type Encounter, type EncounterStatus } from "@/lib/api";

function makeEncounter(overrides: Partial<Encounter> & { id: string }): Encounter {
  return {
    patient_id: "p-001",
    patient_name: null,
    clinician_id: "u-1",
    appointment_id: null,
    specialty: "internal_medicine",
    status: "signed" as EncounterStatus,
    chief_complaint: "",
    vitals: {},
    vital_findings: [],
    subjective: "",
    objective: "",
    assessment: "",
    plan: "",
    patient_instructions: "",
    note_source: "clinician",
    note_model: null,
    editable: false,
    signable: false,
    started_at: "2026-01-01T09:00:00",
    signed_at: null,
    signed_by: null,
    amended_at: null,
    amendment_reason: "",
    clinical_note_id: null,
    orders: [],
    template: { subjective: "", objective: "", assessment: "", plan: "" },
    ...overrides,
  };
}

describe("pickPriorVitals", () => {
  it("picks the newest signed encounter", () => {
    const older = makeEncounter({ id: "e-1", started_at: "2026-01-01T09:00:00", vitals: { weight: 70 } });
    const newer = makeEncounter({ id: "e-2", started_at: "2026-02-01T09:00:00", vitals: { weight: 72 } });
    const result = pickPriorVitals([older, newer], { excludeEncounterId: "e-99" });
    expect(result?.encounterId).toBe("e-2");
    expect(result?.startedAt).toBe("2026-02-01T09:00:00");
  });

  it("ignores drafts", () => {
    const signed = makeEncounter({ id: "e-1", started_at: "2026-01-01T09:00:00", vitals: { weight: 70 } });
    const draft = makeEncounter({
      id: "e-2",
      status: "draft",
      started_at: "2026-02-01T09:00:00",
      vitals: { weight: 80 },
    });
    const result = pickPriorVitals([signed, draft], { excludeEncounterId: "e-99" });
    expect(result?.encounterId).toBe("e-1");
  });

  it("ignores the current encounter even when it is signed and newest", () => {
    const older = makeEncounter({ id: "e-1", started_at: "2026-01-01T09:00:00", vitals: { weight: 70 } });
    const current = makeEncounter({ id: "e-2", started_at: "2026-02-01T09:00:00", vitals: { weight: 80 } });
    const result = pickPriorVitals([older, current], { excludeEncounterId: "e-2" });
    expect(result?.encounterId).toBe("e-1");
  });

  it("returns weight/height only", () => {
    const encounter = makeEncounter({
      id: "e-1",
      vitals: { weight: 80, height: 170, systolic: 150, diastolic: 92, heart_rate: 88, temperature: 37.2 },
    });
    const result = pickPriorVitals([encounter], { excludeEncounterId: "e-99" });
    expect(result?.vitals).toEqual({ weight: 80, height: 170 });
    expect(Object.keys(result!.vitals)).toHaveLength(2);
  });

  it("skips encounters with neither weight nor height", () => {
    const newerBpOnly = makeEncounter({
      id: "e-2",
      started_at: "2026-02-01T09:00:00",
      vitals: { systolic: 130, diastolic: 85 },
    });
    const olderWithWeight = makeEncounter({
      id: "e-1",
      started_at: "2026-01-01T09:00:00",
      vitals: { weight: 70 },
    });
    const result = pickPriorVitals([newerBpOnly, olderWithWeight], { excludeEncounterId: "e-99" });
    expect(result?.encounterId).toBe("e-1");
  });

  it("rejects junk values", () => {
    const junkVitals = {
      weight: 0,
      height: NaN,
      unit: "kg",
      heart_rate: undefined,
    } as unknown as Record<string, number>;
    const encounter = makeEncounter({ id: "e-1", vitals: junkVitals });
    const result = pickPriorVitals([encounter], { excludeEncounterId: "e-99" });
    expect(result).toBeNull();
  });

  it("does not trust server ordering", () => {
    const first = makeEncounter({ id: "e-1", started_at: "2026-01-01T09:00:00", vitals: { weight: 70 } });
    const second = makeEncounter({ id: "e-2", started_at: "2026-02-01T09:00:00", vitals: { weight: 75 } });
    const result = pickPriorVitals([first, second], { excludeEncounterId: "e-99" });
    expect(result?.encounterId).toBe("e-2");
  });

  it("returns null for empty input and for all-drafts input", () => {
    expect(pickPriorVitals([], { excludeEncounterId: "e-99" })).toBeNull();
    const draft = makeEncounter({ id: "e-1", status: "draft", vitals: { weight: 70 } });
    expect(pickPriorVitals([draft], { excludeEncounterId: "e-99" })).toBeNull();
  });

  it("counts amended as signed", () => {
    const amended = makeEncounter({ id: "e-1", status: "amended", vitals: { weight: 70 } });
    const result = pickPriorVitals([amended], { excludeEncounterId: "e-99" });
    expect(result?.encounterId).toBe("e-1");
  });
});
