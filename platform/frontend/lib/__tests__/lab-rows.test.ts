import { describe, expect, it } from "vitest";
import { type LabHistoryEntry, type PatientLabHistory } from "@/lib/api";
import { buildLabRows, isBloodPressure, labStatus, parseSnapshotValue } from "@/lib/lab-rows";

const entry = (value: number, over: Partial<LabHistoryEntry> = {}): LabHistoryEntry => ({
  value,
  taken_at: "2026-10-01T09:00:00",
  is_abnormal: false,
  is_critical: false,
  reference_low: null,
  reference_high: null,
  ...over,
});

const test = (test_name: string, entries: LabHistoryEntry[], unit = "") => ({ test_name, unit, entries });
const name = (n: string) => n;

describe("labStatus", () => {
  it("a critical reading is critical, whatever the range says", () => {
    expect(labStatus(entry(6.4, { is_critical: true, is_abnormal: true, reference_high: 5.1 }))).toBe("critical");
    expect(labStatus(entry(6.4, { is_critical: true }))).toBe("critical");
  });

  it("an abnormal reading says which side of the range it is on", () => {
    expect(labStatus(entry(162, { is_abnormal: true, reference_high: 100 }))).toBe("high");
    expect(labStatus(entry(3.1, { is_abnormal: true, reference_low: 3.5, reference_high: 5.1 }))).toBe("low");
  });

  it("an abnormal reading with no usable range is abnormal, not a guess", () => {
    expect(labStatus(entry(9, { is_abnormal: true }))).toBe("abnormal");
    expect(labStatus(entry(4, { is_abnormal: true, reference_low: 3, reference_high: 5 }))).toBe("abnormal");
  });

  it("a reading that is not flagged is normal", () => {
    expect(labStatus(entry(4.1, { reference_low: 3.5, reference_high: 5.1 }))).toBe("normal");
  });
});

describe("parseSnapshotValue", () => {
  it.each([
    ["6.8%", { value: "6.8", unit: "%" }],
    ["8.2 %", { value: "8.2", unit: "%" }],
    ["102 mg/dL", { value: "102", unit: "mg/dL" }],
    ["6.4 mmol/L", { value: "6.4", unit: "mmol/L" }],
    ["2.4", { value: "2.4", unit: "" }],
    ["2,4", { value: "2.4", unit: "" }],
    ["-3 mEq/L", { value: "-3", unit: "mEq/L" }],
  ])("%s", (raw, expected) => {
    expect(parseSnapshotValue(raw)).toEqual(expected);
  });

  it("leaves what is not a plain number alone, with no unit", () => {
    expect(parseSnapshotValue("138/86")).toEqual({ value: "138/86", unit: "" });
    expect(parseSnapshotValue("pending")).toEqual({ value: "pending", unit: "" });
    expect(parseSnapshotValue("")).toEqual({ value: "", unit: "" });
  });
});

describe("isBloodPressure", () => {
  it.each(["bp", "BP", "bp_systolic", "bp_diastolic", "systolic", "Diastolic"])("%s is a vital sign", (k) => {
    expect(isBloodPressure(k)).toBe(true);
  });
  it.each(["potassium", "hba1c", "bnp", "ldl"])("%s is a lab", (k) => {
    expect(isBloodPressure(k)).toBe(false);
  });
});

describe("buildLabRows", () => {
  it("is empty with nothing from either source", () => {
    expect(buildLabRows(undefined, undefined, name)).toEqual([]);
    expect(buildLabRows({ tests: [] }, {}, name)).toEqual([]);
  });

  it("builds a row from the history: latest value, status, range, date and readings oldest first", () => {
    const history: PatientLabHistory = {
      tests: [
        test(
          "potassium",
          [
            entry(6.4, { taken_at: "2026-10-03T09:00:00", is_critical: true, is_abnormal: true, reference_low: 3.5, reference_high: 5.1 }),
            entry(5.1, { taken_at: "2026-09-03T09:00:00", reference_low: 3.5, reference_high: 5.1 }),
          ],
          "mmol/L",
        ),
      ],
    };

    const [row] = buildLabRows(history, undefined, name);

    expect(row).toMatchObject({
      key: "potassium",
      value: "6.4",
      unit: "mmol/L",
      status: "critical",
      takenAt: "2026-10-03T09:00:00",
      low: 3.5,
      high: 5.1,
      hasHistory: true,
    });
    expect(row.readings.map((r) => r.value)).toEqual([5.1, 6.4]);
  });

  it("shows a test once when both sources have it, with the history's data", () => {
    const history = { tests: [test("potassium", [entry(6.4, { is_critical: true })], "mmol/L")] };

    const rows = buildLabRows(history, { Potassium: "5.0 mmol/L" }, name);

    expect(rows).toHaveLength(1);
    expect(rows[0].value).toBe("6.4");
    expect(rows[0].hasHistory).toBe(true);
  });

  it("matches the two sources through the test-name aliases", () => {
    const history = { tests: [test("hba1c", [entry(8.2, { is_abnormal: true })], "%")] };

    expect(buildLabRows(history, { A1C: "7.9 %" }, name)).toHaveLength(1);
  });

  it("keeps a test that only the snapshot has, honestly: a value, no date, no status, no trend", () => {
    const [row] = buildLabRows(undefined, { creatinine: "2.1 mg/dL" }, name);

    expect(row).toMatchObject({
      key: "creatinine",
      value: "2.1",
      unit: "mg/dL",
      status: "unknown",
      takenAt: null,
      low: null,
      high: null,
      readings: [],
      hasHistory: false,
    });
  });

  it("shows a snapshot value that is not a number as it is, without breaking", () => {
    const [row] = buildLabRows(undefined, { culture: "pending" }, name);

    expect(row).toMatchObject({ value: "pending", unit: "", status: "unknown" });
  });

  it("leaves blood pressure out, from either source", () => {
    const history = { tests: [test("bp_systolic", [entry(150, { is_abnormal: true })], "mmHg"), test("sodium", [entry(139)])] };

    const rows = buildLabRows(history, { bp: "138/86", bp_diastolic: "86", ldl: "102 mg/dL" }, name);

    expect(rows.map((r) => r.key).sort()).toEqual(["ldl", "sodium"]);
  });

  it("skips a test that has no readings", () => {
    expect(buildLabRows({ tests: [test("sodium", [])] }, undefined, name)).toEqual([]);
  });

  it("orders critical, then abnormal, then normal, then those with no history, alphabetically within each", () => {
    const history = {
      tests: [
        test("sodium", [entry(139)]),
        test("calcium", [entry(9.4)]),
        test("ldl", [entry(162, { is_abnormal: true, reference_high: 100 })]),
        test("potassium", [entry(6.4, { is_critical: true })]),
        test("hemoglobin", [entry(8, { is_abnormal: true, reference_low: 12 })]),
      ],
    };

    const rows = buildLabRows(history, { creatinine: "2.1 mg/dL", albumin: "3.0" }, name);

    expect(rows.map((r) => `${r.key}:${r.status}`)).toEqual([
      "potassium:critical",
      "hemoglobin:low",
      "ldl:high",
      "calcium:normal",
      "sodium:normal",
      "albumin:unknown",
      "creatinine:unknown",
    ]);
  });

  it("sorts by the name the clinician reads, not by the key", () => {
    const history = { tests: [test("potassium", [entry(4)]), test("sodium", [entry(139)])] };
    const spanish: Record<string, string> = { potassium: "Zinc-like", sodium: "Antes" };

    const rows = buildLabRows(history, undefined, (n) => spanish[n]);

    expect(rows.map((r) => r.key)).toEqual(["sodium", "potassium"]);
  });
});
