import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import VitalsForm, { type VitalsAutofill } from "@/components/encounters/vitals-form";
import { type VitalSpecOut } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const SPECS: VitalSpecOut[] = [
  { key: "weight", label: "Weight", unit: "kg", min: 1, max: 400, normal_low: 40, normal_high: 120, decimals: 1 },
  { key: "height", label: "Height", unit: "cm", min: 30, max: 250, normal_low: 140, normal_high: 200, decimals: 0 },
];

function renderForm({
  specs = SPECS,
  autofill,
  disabled,
  onChange = vi.fn(),
}: {
  specs?: VitalSpecOut[];
  autofill?: VitalsAutofill;
  disabled?: boolean;
  onChange?: (v: Record<string, number | "">) => void;
} = {}) {
  return render(
    <LanguageProvider>
      <VitalsForm
        vitals={{}}
        specs={specs}
        findings={[]}
        disabled={disabled}
        onChange={onChange}
        autofill={autofill}
      />
    </LanguageProvider>
  );
}

describe("VitalsForm autofill", () => {
  it("shows no button when autofill is not provided", () => {
    renderForm();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows no button when specs lack weight and height, even with autofill", () => {
    renderForm({
      specs: [{ key: "heart_rate", label: "Heart rate", unit: "bpm", min: 30, max: 220, normal_low: 60, normal_high: 100, decimals: 0 }],
      autofill: { onApply: vi.fn(), loading: false, sourceDate: null },
    });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("is enabled and labelled with the source date", () => {
    renderForm({ autofill: { onApply: vi.fn(), loading: false, sourceDate: "2026-06-01T09:00:00" } });
    const button = screen.getByRole("button", { name: "Autofill weight & height" });
    expect(button).toBeEnabled();
    expect(screen.getByText(/From the signed visit of/)).toBeInTheDocument();
  });

  it("calls onApply once when clicked", () => {
    const onApply = vi.fn();
    renderForm({ autofill: { onApply, loading: false, sourceDate: "2026-06-01T09:00:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Autofill weight & height" }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it("honours the disabled prop by hiding the control entirely", () => {
    const onApply = vi.fn();
    renderForm({ disabled: true, autofill: { onApply, loading: false, sourceDate: "2026-06-01T09:00:00" } });
    expect(screen.queryByRole("button", { name: "Autofill weight & height" })).not.toBeInTheDocument();
  });

  it("shows the empty hint and a disabled button when there is no source", () => {
    renderForm({ autofill: { onApply: vi.fn(), loading: false, sourceDate: null } });
    expect(screen.getByText("No signed visit with a recorded weight or height.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Autofill weight & height" })).toBeDisabled();
  });

  it("shows the loading hint and a disabled button while loading", () => {
    renderForm({ autofill: { onApply: vi.fn(), loading: true, sourceDate: null } });
    expect(screen.getByText("Looking for a previous visit…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Autofill weight & height" })).toBeDisabled();
  });

  it("always shows the static note alongside the control", () => {
    renderForm({ autofill: { onApply: vi.fn(), loading: false, sourceDate: null } });
    expect(
      screen.getByText("Only weight and height are copied. Every other vital must be measured at this visit.")
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
