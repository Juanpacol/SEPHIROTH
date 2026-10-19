import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import VitalsForm, { type VitalsAutofill } from "@/components/encounters/vitals-form";
import { type AutofillSummary } from "@/lib/vitals-autofill";
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

const EMPTY = { copy: [], filled: [], missing: [] } as AutofillSummary;
const ready = (copy: AutofillSummary["copy"], rest: Partial<AutofillSummary> = {}): VitalsAutofill => ({
  onApply: vi.fn(),
  status: "ready",
  summary: { ...EMPTY, copy, ...rest },
});
const WEIGHT_78 = { key: "weight" as const, value: 78, at: "2026-07-12T09:00:00" };
const HEIGHT_170 = { key: "height" as const, value: 170, at: "2026-03-03T09:00:00" };

describe("VitalsForm autofill", () => {
  it("shows no button when autofill is not provided", () => {
    renderForm();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows no button when specs lack weight and height, even with autofill", () => {
    renderForm({ specs: [spec("heart_rate", "Heart rate", "bpm")], autofill: ready([WEIGHT_78]) });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("honours the disabled prop by hiding the control entirely", () => {
    renderForm({ disabled: true, autofill: ready([WEIGHT_78]) });
    expect(screen.queryByRole("button", { name: BUTTON })).not.toBeInTheDocument();
  });

  it("calls onApply once when clicked", () => {
    const autofill = ready([WEIGHT_78, HEIGHT_170]);
    renderForm({ autofill });
    fireEvent.click(screen.getByRole("button", { name: BUTTON }));
    expect(autofill.onApply).toHaveBeenCalledTimes(1);
  });

  it("says exactly what it will copy, and from which visit, when there is something to fill", () => {
    renderForm({ autofill: ready([WEIGHT_78, HEIGHT_170]) });

    expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
    expect(
      screen.getByText("Will copy weight 78.0 kg (visit of Jul 12, 2026) and height 170 cm (visit of Mar 3, 2026)."),
    ).toBeInTheDocument();
  });

  it("copies the one value there is and says which one has no earlier reading", () => {
    renderForm({ autofill: ready([WEIGHT_78], { missing: ["height"] }) });

    expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
    expect(
      screen.getByText("Will copy weight 78.0 kg (visit of Jul 12, 2026). No earlier height recorded."),
    ).toBeInTheDocument();
  });

  it("explains that nothing can be copied when the patient has no signed visit with either", () => {
    renderForm({ autofill: { onApply: vi.fn(), status: "none", summary: { ...EMPTY, missing: ["weight", "height"] } } });

    expect(
      screen.getByText(
        "This patient has no signed visit with weight or height yet. They will be recorded when you sign this one.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUTTON })).toBeDisabled();
  });

  it("says they are already filled, and from which visit when the values match it", () => {
    renderForm({
      autofill: {
        onApply: vi.fn(),
        status: "filled",
        summary: {
          ...EMPTY,
          filled: [
            { key: "weight", at: "2026-07-12T09:00:00" },
            { key: "height", at: "2026-07-12T09:00:00" },
          ],
        },
      },
    });

    expect(
      screen.getByText("Already filled: weight (visit of Jul 12, 2026) and height (visit of Jul 12, 2026)."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUTTON })).toBeDisabled();
  });

  it("names each field's own visit when they come from different ones", () => {
    renderForm({
      autofill: {
        onApply: vi.fn(),
        status: "filled",
        summary: {
          ...EMPTY,
          filled: [
            { key: "weight", at: "2026-07-12T09:00:00" },
            { key: "height", at: "2026-03-03T09:00:00" },
          ],
        },
      },
    });

    expect(
      screen.getByText("Already filled: weight (visit of Jul 12, 2026) and height (visit of Mar 3, 2026)."),
    ).toBeInTheDocument();
  });

  it("does not claim a visit for values the clinician typed", () => {
    renderForm({
      autofill: {
        onApply: vi.fn(),
        status: "filled",
        summary: { ...EMPTY, filled: [{ key: "weight", at: null }], missing: ["height"] },
      },
    });

    const line = screen.getByText(/Already filled: weight\./);
    expect(line.textContent).toBe("Already filled: weight. No earlier height recorded.");
    expect(line.textContent).not.toMatch(/visit of/);
  });

  it("explains a half-filled visit: one field filled, the other copied", () => {
    renderForm({ autofill: ready([HEIGHT_170], { filled: [{ key: "weight", at: null }] }) });

    expect(
      screen.getByText("Will copy height 170 cm (visit of Mar 3, 2026). Already filled: weight."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUTTON })).toBeEnabled();
  });

  it("shows the loading hint and a disabled button while loading", () => {
    renderForm({ autofill: { onApply: vi.fn(), status: "loading", summary: EMPTY } });
    expect(screen.getByText("Looking for a previous visit…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: BUTTON })).toBeDisabled();
  });

  it("always shows the note that only weight and height are copied, whatever the state", () => {
    const note =
      "Only weight and height are copied. The other vitals show the last reading as a reference and must be measured at this visit.";
    for (const status of ["none", "loading", "filled", "ready"] as const) {
      const { unmount } = renderForm({ autofill: { onApply: vi.fn(), status, summary: EMPTY } });
      expect(screen.getByText(note)).toBeVisible();
      unmount();
    }
  });

  it("ties the disabled button to its reason and to the note for screen readers", () => {
    renderForm({ autofill: { onApply: vi.fn(), status: "none", summary: { ...EMPTY, missing: ["weight", "height"] } } });

    const button = screen.getByRole("button", { name: BUTTON });
    const described = (button.getAttribute("aria-describedby") ?? "").split(" ");
    const texts = described.map((id) => document.getElementById(id)?.textContent ?? "");

    expect(button).toBeDisabled();
    expect(texts[0]).toMatch(/no signed visit with weight or height/);
    expect(texts[1]).toMatch(/Only weight and height are copied/);
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

describe("VitalsForm autofill in Spanish", () => {
  afterEach(() => localStorage.removeItem("cac_lang"));

  it("explains each state in Spanish, with Spanish dates and the same facts", async () => {
    localStorage.setItem("cac_lang", "es");

    renderForm({ autofill: ready([WEIGHT_78], { missing: ["height"] }) });
    expect(
      await screen.findByText("Copiará peso 78.0 kg (visita del 12 jul 2026). Sin talla en visitas anteriores."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Solo se copian el peso y la talla\./)).toBeInTheDocument();
  });

  it("says in Spanish why nothing can be copied", async () => {
    localStorage.setItem("cac_lang", "es");

    renderForm({ autofill: { onApply: vi.fn(), status: "none", summary: { ...EMPTY, missing: ["weight", "height"] } } });

    expect(
      await screen.findByText(
        "Este paciente aún no tiene una consulta firmada con peso o talla. Se registrarán al firmar esta.",
      ),
    ).toBeInTheDocument();
  });

  it("joins the names the Spanish way", async () => {
    localStorage.setItem("cac_lang", "es");

    renderForm({
      autofill: {
        onApply: vi.fn(),
        status: "filled",
        summary: { ...EMPTY, filled: [{ key: "weight", at: null }, { key: "height", at: null }] },
      },
    });

    expect(await screen.findByText("Ya están rellenos: peso y talla.")).toBeInTheDocument();
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
