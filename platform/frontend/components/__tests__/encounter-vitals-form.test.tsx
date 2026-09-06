/** Vitals entry.
 *
 * The property under test is that a blood pressure is one field. A form with
 * two boxes for it is a form that gets one box filled, and a lone systolic is a
 * reading nobody can act on — so an unparseable entry clears both halves rather
 * than leaving a stale one behind.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import VitalsForm from "@/components/encounters/vitals-form";
import type { Encounter, VitalSpecOut } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const SPECS: VitalSpecOut[] = [
  {
    key: "systolic",
    label: "Presión sistólica",
    unit: "mmHg",
    min: 40,
    max: 300,
    normal_low: 90,
    normal_high: 130,
    decimals: 0,
  },
  {
    key: "diastolic",
    label: "Presión diastólica",
    unit: "mmHg",
    min: 20,
    max: 200,
    normal_low: 60,
    normal_high: 85,
    decimals: 0,
  },
  {
    key: "heart_rate",
    label: "Frecuencia cardíaca",
    unit: "lpm",
    min: 20,
    max: 250,
    normal_low: 60,
    normal_high: 100,
    decimals: 0,
  },
];

const HIGH_BP: Encounter["vital_findings"] = [
  {
    key: "systolic",
    label: "Presión sistólica",
    display: "210 mmHg",
    severity: "high",
    detail: "Presión sistólica alto: 210 mmHg (normal 90–130 mmHg)",
  },
];

function renderForm(
  vitals: Record<string, number> = {},
  findings: Encounter["vital_findings"] = [],
  disabled = false,
) {
  const onChange = vi.fn();
  render(
    <LanguageProvider>
      <VitalsForm
        vitals={vitals}
        specs={SPECS}
        findings={findings}
        disabled={disabled}
        onChange={onChange}
      />
    </LanguageProvider>,
  );
  return onChange;
}

function bpField() {
  return screen.getByPlaceholderText("120/80");
}

describe("VitalsForm", () => {
  it("renders blood pressure as one field, not two", () => {
    renderForm();

    expect(bpField()).toBeInTheDocument();
    expect(screen.queryByLabelText(/Presión sistólica/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Presión diastólica/)).not.toBeInTheDocument();
  });

  it("splits a typed pair into both halves", () => {
    const onChange = renderForm();

    fireEvent.change(bpField(), { target: { value: "210/120" } });
    fireEvent.blur(bpField());

    expect(onChange).toHaveBeenCalledWith({ systolic: 210, diastolic: 120 });
  });

  it("shows a stored pair back as one reading", () => {
    renderForm({ systolic: 120, diastolic: 80 });

    expect(bpField()).toHaveValue("120/80");
  });

  it("clears both halves when the entry stops being a pair", () => {
    const onChange = renderForm({ systolic: 120, diastolic: 80 });

    fireEvent.change(bpField(), { target: { value: "120" } });
    fireEvent.blur(bpField());

    // Not `{systolic: 120}`: a systolic left over from a previous reading is
    // worse than a blank.
    expect(onChange).toHaveBeenCalledWith({ systolic: "", diastolic: "" });
  });

  it("marks an abnormal reading and says what normal is", () => {
    renderForm({ systolic: 210, diastolic: 120 }, HIGH_BP);

    expect(bpField()).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/normal 90–130 mmHg/)).toBeInTheDocument();
  });

  it("leaves a normal reading unmarked", () => {
    renderForm({ systolic: 120, diastolic: 80 });

    expect(bpField()).not.toHaveAttribute("aria-invalid");
  });

  it("passes other vitals through as numbers", () => {
    const onChange = renderForm();

    fireEvent.change(screen.getByLabelText("Frecuencia cardíaca"), { target: { value: "72" } });

    expect(onChange).toHaveBeenCalledWith({ heart_rate: 72 });
  });

  it("sends an empty string rather than zero for a cleared field", () => {
    const onChange = renderForm({ heart_rate: 72 });

    fireEvent.change(screen.getByLabelText("Frecuencia cardíaca"), { target: { value: "" } });

    expect(onChange).toHaveBeenCalledWith({ heart_rate: "" });
  });

  it("is inert on a signed encounter", () => {
    renderForm({ systolic: 120, diastolic: 80 }, [], true);

    expect(bpField()).toBeDisabled();
    expect(screen.getByLabelText("Frecuencia cardíaca")).toBeDisabled();
  });
});
