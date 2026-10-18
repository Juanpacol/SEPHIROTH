import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import VitalsForm, { type VitalsAutofill } from "@/components/encounters/vitals-form";
import { type LastVitalReading, type VitalSpecOut } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const spec = (key: string, label: string, unit: string, decimals = 0): VitalSpecOut => ({
  key,
  label,
  unit,
  min: 1,
  max: 400,
  normal_low: 1,
  normal_high: 400,
  decimals,
});

const SPECS: VitalSpecOut[] = [spec("weight", "Weight", "kg", 1), spec("height", "Height", "cm")];

const ALL_SPECS: VitalSpecOut[] = [
  spec("systolic", "Systolic", "mmHg"),
  spec("diastolic", "Diastolic", "mmHg"),
  spec("heart_rate", "Heart rate", "bpm"),
  spec("temperature", "Temperature", "°C", 1),
  spec("pain_score", "Pain", ""),
  ...SPECS,
];

const reading = (value: number, encounter_id = "e-1", at = "2026-10-01T09:00:00"): LastVitalReading => ({
  value,
  at,
  encounter_id,
});

function renderForm({
  specs = SPECS,
  autofill,
  disabled,
  lastReadings,
  vitals = {},
  onChange = vi.fn(),
}: {
  specs?: VitalSpecOut[];
  autofill?: VitalsAutofill;
  disabled?: boolean;
  lastReadings?: Record<string, LastVitalReading>;
  vitals?: Record<string, number>;
  onChange?: (v: Record<string, number | "">) => void;
} = {}) {
  return render(
    <LanguageProvider>
      <VitalsForm
        vitals={vitals}
        specs={specs}
        findings={[]}
        disabled={disabled}
        onChange={onChange}
        autofill={autofill}
        lastReadings={lastReadings}
      />
    </LanguageProvider>,
  );
}

const BUTTON = "Autofill weight & height";

describe("VitalsForm autofill", () => {
  it("shows no button when autofill is not provided", () => {
    renderForm();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows no button when specs lack weight and height, even with autofill", () => {
    renderForm({
      specs: [spec("heart_rate", "Heart rate", "bpm")],
      autofill: { onApply: vi.fn(), status: "ready" },
    });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("is enabled and explains it only fills empty fields when there is something to fill", () => {
    renderForm({ autofill: { onApply: vi.fn(), status: "ready" } });
    expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
    expect(screen.getByText("Fills only the empty fields, from the latest recorded values.")).toBeInTheDocument();
  });

  it("calls onApply once when clicked", () => {
    const onApply = vi.fn();
    renderForm({ autofill: { onApply, status: "ready" } });
    fireEvent.click(screen.getByRole("button", { name: BUTTON }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it("honours the disabled prop by hiding the control entirely", () => {
    renderForm({ disabled: true, autofill: { onApply: vi.fn(), status: "ready" } });
    expect(screen.queryByRole("button", { name: BUTTON })).not.toBeInTheDocument();
  });

  it("shows the empty hint and a disabled button when no earlier visit has weight or height", () => {
    renderForm({ autofill: { onApply: vi.fn(), status: "none" } });
    expect(screen.getByText("No weight or height recorded in earlier visits.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUTTON })).toBeDisabled();
  });

  it("says so, and disables the button, when both fields are already filled", () => {
    renderForm({ autofill: { onApply: vi.fn(), status: "filled" } });
    expect(screen.getByText("Weight and height are already filled.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUTTON })).toBeDisabled();
  });

  it("shows the loading hint and a disabled button while loading", () => {
    renderForm({ autofill: { onApply: vi.fn(), status: "loading" } });
    expect(screen.getByText("Looking for a previous visit…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUTTON })).toBeDisabled();
  });

  it("always shows the static note alongside the control", () => {
    renderForm({ autofill: { onApply: vi.fn(), status: "none" } });
    expect(
      screen.getByText("Only weight and height are copied. Every other vital must be measured at this visit."),
    ).toBeInTheDocument();
  });

  it("still fires onChange for manual weight input and blood pressure (regression)", () => {
    const onChange = vi.fn();
    renderForm({ onChange });

    fireEvent.change(screen.getByLabelText("Weight"), { target: { value: "72" } });
    expect(onChange).toHaveBeenCalledWith({ weight: 72 });

    const bp = screen.getByLabelText("Blood pressure");
    fireEvent.change(bp, { target: { value: "120/80" } });
    fireEvent.blur(bp);
    expect(onChange).toHaveBeenCalledWith({ systolic: 120, diastolic: 80 });
  });
});

describe("VitalsForm last readings", () => {
  it("shows no reference at all when lastReadings is not provided", () => {
    renderForm({ specs: ALL_SPECS });
    expect(screen.queryByText(/Last:/)).not.toBeInTheDocument();
    expect(screen.queryByText("No previous reading")).not.toBeInTheDocument();
  });

  it("shows each vital's last reading with its unit and date", () => {
    renderForm({
      specs: ALL_SPECS,
      lastReadings: {
        heart_rate: reading(64),
        temperature: reading(36.6),
        weight: reading(70),
        height: reading(170),
        pain_score: reading(0),
      },
    });

    expect(screen.getByText("Last: 64 bpm · Oct 1, 2026")).toBeInTheDocument();
    expect(screen.getByText("Last: 36.6 °C · Oct 1, 2026")).toBeInTheDocument();
    expect(screen.getByText("Last: 70.0 kg · Oct 1, 2026")).toBeInTheDocument();
    expect(screen.getByText("Last: 170 cm · Oct 1, 2026")).toBeInTheDocument();
    // A pain score of 0 is a real answer, and has no unit.
    expect(screen.getByText("Last: 0 · Oct 1, 2026")).toBeInTheDocument();
  });

  it("shows blood pressure as one reading", () => {
    renderForm({
      specs: ALL_SPECS,
      lastReadings: { systolic: reading(130, "e-9"), diastolic: reading(85, "e-9") },
    });

    expect(screen.getByText("Last: 130/85 mmHg · Oct 1, 2026")).toBeInTheDocument();
  });

  it("never shows a pressure assembled from two different visits", () => {
    renderForm({
      specs: ALL_SPECS,
      lastReadings: { systolic: reading(150, "e-2"), diastolic: reading(85, "e-1") },
    });

    expect(screen.queryByText(/150\/85/)).not.toBeInTheDocument();
  });

  it("says there is no previous reading for a vital with no history", () => {
    renderForm({ specs: ALL_SPECS, lastReadings: {} });

    // One line per field: pressure + heart rate + temperature + pain + weight + height.
    expect(screen.getAllByText("No previous reading")).toHaveLength(6);
  });

  it("is plain text: nothing to click, and it does not touch the value", () => {
    const onChange = vi.fn();
    renderForm({ specs: ALL_SPECS, lastReadings: { heart_rate: reading(64) }, onChange });

    const line = screen.getByText("Last: 64 bpm · Oct 1, 2026");
    fireEvent.click(line);

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Heart rate")).toHaveValue(null);
    expect(line.closest("button")).toBeNull();
  });

  it("is described to assistive technology as part of its field", () => {
    renderForm({ specs: ALL_SPECS, lastReadings: { heart_rate: reading(64) } });

    const field = screen.getByLabelText("Heart rate");
    const describedBy = field.getAttribute("aria-describedby")!;
    expect(document.getElementById(describedBy)).toHaveTextContent("Last: 64 bpm · Oct 1, 2026");
  });
});
