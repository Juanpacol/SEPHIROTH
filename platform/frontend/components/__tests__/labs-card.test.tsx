import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LabsCard from "@/components/patients/labs-card";
import { api, type LabHistoryEntry, type LabReviewState, type PatientLabHistory } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const entry = (value: number, over: Partial<LabHistoryEntry> = {}): LabHistoryEntry => ({
  value,
  taken_at: "2026-10-03T09:00:00",
  is_abnormal: false,
  is_critical: false,
  reference_low: null,
  reference_high: null,
  ...over,
});

const HISTORY: PatientLabHistory = {
  tests: [
    { test_name: "sodium", unit: "mmol/L", entries: [entry(139, { reference_low: 135, reference_high: 145 })] },
    {
      test_name: "potassium",
      unit: "mmol/L",
      entries: [
        entry(6.4, { is_critical: true, is_abnormal: true, reference_low: 3.5, reference_high: 5.1 }),
        entry(5.1, { taken_at: "2026-09-03T09:00:00", reference_low: 3.5, reference_high: 5.1 }),
      ],
    },
    { test_name: "ldl", unit: "mg/dL", entries: [entry(162, { is_abnormal: true, reference_high: 100 })] },
    { test_name: "bp_systolic", unit: "mmHg", entries: [entry(150, { is_abnormal: true })] },
  ],
};

function renderCard(snapshot: Record<string, string> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <LabsCard patientId="p-1" snapshot={snapshot} />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

/** The reference range is split across two spans (the range itself never wraps),
 * and holds a non-breaking space before the unit: match on the whole text. */
const wholeText = (text: string) => (_: string, el: Element | null) =>
  el?.tagName === "SPAN" && el.children.length <= 1 && (el.textContent ?? "").replace(/\u00a0/g, " ") === text;

const rows = () => within(screen.getByRole("list")).getAllByRole("listitem");
const mockHistory = (data: PatientLabHistory | Promise<PatientLabHistory>) =>
  vi.spyOn(api, "patientLabHistory").mockImplementation(() => Promise.resolve(data));

describe("LabsCard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem("cac_lang");
  });

  it("is one card, one row per test, most urgent first", async () => {
    mockHistory(HISTORY);
    renderCard();

    await waitFor(() => expect(rows()).toHaveLength(3));
    expect(rows().map((r) => within(r).getByText(/Potassium|Sodium|LDL/).textContent)).toEqual([
      "Potassium",
      "LDL cholesterol",
      "Sodium",
    ]);
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
  });

  it("gives each row its value with unit, a status in words, its range and its date", async () => {
    mockHistory(HISTORY);
    renderCard();
    await waitFor(() => expect(rows()).toHaveLength(3));

    const [potassium, ldl, sodium] = rows();
    expect(within(potassium).getByText("6.4 mmol/L")).toBeInTheDocument();
    expect(within(potassium).getByText("Critical")).toBeInTheDocument();
    expect(within(potassium).getByText(wholeText("Reference 3.5–5.1 mmol/L"))).toBeInTheDocument();
    expect(within(potassium).getByText(/2 readings/)).toBeInTheDocument();

    expect(within(ldl).getByText("High")).toBeInTheDocument();
    expect(within(ldl).getByText(wholeText("Reference ≤ 100 mg/dL"))).toBeInTheDocument();

    expect(within(sodium).getByText("Normal")).toBeInTheDocument();
    expect(within(sodium).queryByText(/readings/)).not.toBeInTheDocument();
  });

  it("draws a trend only where there are two readings, and describes it as text", async () => {
    mockHistory(HISTORY);
    renderCard();
    await waitFor(() => expect(rows()).toHaveLength(3));

    const [potassium, , sodium] = rows();
    expect(within(potassium).getByRole("img")).toHaveAccessibleName(/Potassium: 5\.1 \(.+\) → 6\.4 \(.+\)/);
    expect(within(sodium).queryByRole("img")).not.toBeInTheDocument();
  });

  it("leaves blood pressure out", async () => {
    mockHistory(HISTORY);
    renderCard({ bp: "138/86", bp_diastolic: "86" });
    await waitFor(() => expect(rows()).toHaveLength(3));

    expect(screen.queryByText(/Blood pressure|Systolic|138\/86/)).not.toBeInTheDocument();
  });

  it("shows a snapshot-only test with its value, marked as having no history", async () => {
    mockHistory(HISTORY);
    renderCard({ creatinine: "2.1 mg/dL", hba1c: "6.8%" });

    await waitFor(() => expect(rows()).toHaveLength(5));
    const creatinine = rows().find((r) => within(r).queryByText(/Creatinine/))!;
    expect(within(creatinine).getByText("2.1 mg/dL")).toBeInTheDocument();
    expect(within(creatinine).getByText("No history")).toBeInTheDocument();
    expect(within(creatinine).queryByRole("img")).not.toBeInTheDocument();
    expect(within(creatinine).queryByText(/Critical|High|Low|Abnormal|Normal/)).not.toBeInTheDocument();
    // They sit after every test that has a history.
    expect(rows().slice(-2).map((r) => within(r).queryByText("No history") !== null)).toEqual([true, true]);
  });

  it("shows a test once when the snapshot repeats one the history has", async () => {
    mockHistory(HISTORY);
    renderCard({ Potassium: "5.0 mmol/L" });
    await waitFor(() => expect(rows()).toHaveLength(3));

    expect(screen.getAllByText("Potassium")).toHaveLength(1);
    expect(screen.queryByText("5.0 mmol/L")).not.toBeInTheDocument();
  });

  it("shows a loading state, then an empty one when there is nothing at all", async () => {
    mockHistory({ tests: [] });
    renderCard();

    expect(screen.getByText("Loading labs…")).toBeInTheDocument();
    expect(await screen.findByText("No lab results recorded yet.")).toBeInTheDocument();
  });

  it("still shows the snapshot when the history cannot be loaded", async () => {
    vi.spyOn(api, "patientLabHistory").mockRejectedValue(new Error("500"));
    renderCard({ creatinine: "2.1 mg/dL" });

    expect(await screen.findByText("2.1 mg/dL")).toBeInTheDocument();
  });

  it("speaks Spanish: names, statuses, range and dates", async () => {
    localStorage.setItem("cac_lang", "es");
    mockHistory(HISTORY);
    renderCard({ creatinine: "2.1 mg/dL" });

    expect(await screen.findByText("Laboratorios")).toBeInTheDocument();
    await waitFor(() => expect(rows()).toHaveLength(4));
    expect(screen.getByText("Crítico")).toBeInTheDocument();
    expect(screen.getByText(wholeText("Referencia 3.5–5.1 mmol/L"))).toBeInTheDocument();
    expect(screen.getByText("Sin historial")).toBeInTheDocument();
    expect(screen.getByText(/2 lecturas/)).toBeInTheDocument();
  });
});

describe("LabsCard: review state", () => {
  const review = (over: Partial<LabReviewState> = {}): LabReviewState => ({
    id: "rv-1",
    status: "reviewed",
    disposition: "action_taken",
    reviewed_at: "2026-10-11T08:00:00",
    reviewed_by: "Dra. Ruiz",
    communicated_at: null,
    ...over,
  });
  const one = (r: LabReviewState | null, e: LabHistoryEntry = entry(139)): PatientLabHistory => ({
    tests: [{ test_name: "sodium", unit: "mmol/L", entries: [e], review: r }],
  });
  const state = () => within(rows()[0]).queryByTestId("lab-review");

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem("cac_lang");
  });

  it.each([
    ["received", "Not reviewed"],
    ["reviewed", "Reviewed"],
    ["communicated", "Patient told"],
    ["closed", "Closed"],
  ] as const)("says %s in words", async (status, word) => {
    vi.spyOn(api, "patientLabHistory").mockResolvedValue(one(review({ status })));
    renderCard();
    await waitFor(() => expect(rows()).toHaveLength(1));

    expect(within(state()!).getByText(word)).toBeInTheDocument();
  });

  it("says what was decided, by whom and when", async () => {
    vi.spyOn(api, "patientLabHistory").mockResolvedValue(one(review()));
    renderCard();
    await waitFor(() => expect(rows()).toHaveLength(1));

    expect(state()!.textContent).toContain("Action taken");
    expect(state()!.textContent).toContain("Dra. Ruiz");
    expect(state()!.textContent).toMatch(/\d{1,2}\/\d{1,2}\/2026/);
  });

  it("says when the patient was told", async () => {
    vi.spyOn(api, "patientLabHistory").mockResolvedValue(
      one(review({ status: "communicated", disposition: "needs_patient_contact", communicated_at: "2026-10-12T08:00:00" })),
    );
    renderCard();
    await waitFor(() => expect(rows()).toHaveLength(1));

    expect(state()!.textContent).toMatch(/told \d{1,2}\/\d{1,2}\/2026/);
  });

  it("makes a critical result nobody has reviewed stand out from an ordinary one", async () => {
    vi.spyOn(api, "patientLabHistory").mockResolvedValue({
      tests: [
        {
          test_name: "potassium",
          unit: "mmol/L",
          entries: [entry(6.4, { is_critical: true, is_abnormal: true })],
          review: review({ status: "received", disposition: null, reviewed_by: null, reviewed_at: null }),
        },
        { test_name: "sodium", unit: "mmol/L", entries: [entry(139)], review: review({ status: "received", disposition: null }) },
      ],
    });
    renderCard();
    await waitFor(() => expect(rows()).toHaveLength(2));

    const [critical, ordinary] = rows().map((r) => within(r).getByText("Not reviewed"));
    expect(critical.className).toContain("text-danger");
    expect(ordinary.className).not.toContain("text-danger");
  });

  it("draws nothing for a result with no review, not even the words 'not reviewed'", async () => {
    vi.spyOn(api, "patientLabHistory").mockResolvedValue(one(null));
    renderCard({ creatinine: "2.1 mg/dL" });
    await waitFor(() => expect(rows()).toHaveLength(2));

    expect(screen.queryByTestId("lab-review")).not.toBeInTheDocument();
    expect(screen.queryByText(/Not reviewed/)).not.toBeInTheDocument();
  });

  it("links to the results inbox for that patient, on the list the result is in", async () => {
    vi.spyOn(api, "patientLabHistory").mockResolvedValue(one(review({ status: "reviewed" })));
    const { unmount } = renderCard();
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(within(state()!).getByRole("link", { name: "Open in results" })).toHaveAttribute(
      "href",
      "/results?patient=p-1&filter=open",
    );
    unmount();

    vi.spyOn(api, "patientLabHistory").mockResolvedValue(one(review({ status: "closed" })));
    renderCard();
    await waitFor(() => expect(rows()).toHaveLength(1));
    expect(within(state()!).getByRole("link", { name: "Open in results" })).toHaveAttribute(
      "href",
      "/results?patient=p-1&filter=closed",
    );
  });

  it("speaks Spanish", async () => {
    localStorage.setItem("cac_lang", "es");
    vi.spyOn(api, "patientLabHistory").mockResolvedValue(one(review({ status: "communicated", communicated_at: "2026-10-12T08:00:00" })));
    renderCard();
    await waitFor(() => expect(rows()).toHaveLength(1));

    expect(within(state()!).getByText("Paciente informado")).toBeInTheDocument();
    expect(within(state()!).getByRole("link", { name: "Abrir en resultados" })).toBeInTheDocument();
    expect(state()!.textContent).toContain("Conducta tomada");
  });
});
