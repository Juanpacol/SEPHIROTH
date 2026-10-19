import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import InformPatientSheet from "@/components/results/inform-patient-sheet";
import { ToastProvider } from "@/components/ui/toast";
import { api, ApiError, type ResultReview, type ShareableEvent } from "@/lib/api";
import { LanguageProvider, useLanguage } from "@/lib/language";

function ToSpanish() {
  const { setLang } = useLanguage();
  return (
    <button type="button" onClick={() => setLang("es")}>
      to-es
    </button>
  );
}

const review = (over: Partial<ResultReview> = {}): ResultReview =>
  ({
    id: "r-1",
    result_type: "lab",
    result_id: "10",
    patient_id: "p-1",
    patient_name: "Ana Gómez",
    status: "reviewed",
    severity: "critical",
    classification_reason: "",
    disposition: "needs_patient_contact",
    note: "private note",
    reviewed_at: null,
    reviewed_by: null,
    share_id: null,
    task_id: null,
    closed_at: null,
    created_at: "2026-10-10T08:00:00",
    needs_communication: true,
    closable: false,
    result: { kind: "lab", test_name: "potassium", value: 6.2, unit: "mEq/L", taken_at: "2026-10-10T08:00:00" },
    ...over,
  }) as ResultReview;

const entry = (id: number, over: Partial<ShareableEvent> = {}): ShareableEvent =>
  ({
    timeline_event_id: id,
    already_shared: false,
    id,
    date: "2026-10-09",
    type: "lab",
    title: `Entry ${id}`,
    detail: "",
    ai_generated: false,
    ...over,
  }) as ShareableEvent;

function renderSheet(props: { review?: ResultReview | null; onClose?: () => void; onDone?: (r: ResultReview) => void } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const element = (r: ResultReview | null) => (
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <ToastProvider>
          <ToSpanish />
          <InformPatientSheet review={r} onClose={props.onClose ?? vi.fn()} onDone={props.onDone ?? vi.fn()} />
        </ToastProvider>
      </LanguageProvider>
    </QueryClientProvider>
  );
  const view = render(element(props.review === undefined ? review() : props.review));
  return { ...view, rerenderWith: (r: ResultReview | null) => view.rerender(element(r)) };
}

const messageBox = () => screen.getByLabelText("Message to the patient") as HTMLTextAreaElement;
const send = () => screen.getByRole("button", { name: "Send to the patient" });

describe("InformPatientSheet", () => {
  let communicate: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    communicate = vi
      .spyOn(api, "communicateResult")
      .mockResolvedValue({ ...review({ status: "communicated" }), patient_notified: true });
    vi.spyOn(api, "shareableEvents").mockResolvedValue([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem("cac_lang");
  });

  it("renders nothing while there is no result to tell", () => {
    renderSheet({ review: null });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("Tell the patient")).not.toBeInTheDocument();
  });

  it("shows which result it is about, and the decision, but never the private note", () => {
    renderSheet();

    expect(screen.getByText("Potassium")).toBeInTheDocument();
    expect(screen.getByText("6.2 mEq/L")).toBeInTheDocument();
    expect(screen.getByText(/Ana Gómez · The patient needs to be told/)).toBeInTheDocument();
    expect(screen.queryByText(/private note/)).not.toBeInTheDocument();
  });

  it("starts the message from a suggestion that names the test and the value, and lets it be rewritten", () => {
    renderSheet();

    expect(messageBox().value).toBe(
      "Hello, we reviewed your result for Potassium: 6.2 mEq/L. We would like to talk with you about it. Please contact the clinic to arrange the next step.",
    );
    fireEvent.change(messageBox(), { target: { value: "Call me." } });
    expect(messageBox().value).toBe("Call me.");
  });

  it("has an imaging suggestion without a value", () => {
    renderSheet({
      review: review({
        result_type: "imaging",
        result: { kind: "imaging", modality: "cr", body_part: "chest" } as ResultReview["result"],
      }),
    });

    expect(messageBox().value).toContain("your CR chest study");
    expect(messageBox().value).not.toContain("()");
  });

  it("never sends a blank message, and counts and caps what is written", () => {
    renderSheet();

    fireEvent.change(messageBox(), { target: { value: "   " } });
    expect(send()).toBeDisabled();
    fireEvent.change(messageBox(), { target: { value: "Hola" } });
    expect(send()).toBeEnabled();
    expect(messageBox()).toHaveAttribute("maxlength", "2000");
    expect(screen.getByText("4 / 2,000")).toBeInTheDocument();
  });

  it("sends the trimmed message with no timeline entry, so the server makes one, then tells the page", async () => {
    const onDone = vi.fn();
    renderSheet({ onDone });
    fireEvent.change(messageBox(), { target: { value: "  Hola, llámenos.  " } });

    fireEvent.click(send());

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(communicate).toHaveBeenCalledWith("r-1", { message: "Hola, llámenos." });
    expect(await screen.findByText("The patient has been told and notified.")).toBeInTheDocument();
  });

  it("says plainly when nobody was notified because the patient has no portal access", async () => {
    communicate.mockResolvedValue({ ...review({ status: "communicated" }), patient_notified: false });
    renderSheet();

    fireEvent.click(send());

    expect(
      await screen.findByText("Recorded. This patient has no portal access yet, so tell them another way."),
    ).toBeInTheDocument();
  });

  it("offers only entries that were not shared yet, and sends the one picked", async () => {
    vi.spyOn(api, "shareableEvents").mockResolvedValue([entry(5), entry(6, { already_shared: true })]);
    renderSheet();

    const select = (await screen.findByLabelText(/Use one of the patient's timeline entries/)) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      "Make an entry from this result",
      "Entry 5 · 2026-10-09",
    ]);
    fireEvent.change(select, { target: { value: "5" } });
    fireEvent.click(send());

    await waitFor(() => expect(communicate).toHaveBeenCalled());
    expect(communicate.mock.calls[0][1]).toMatchObject({ timeline_event_id: 5 });
  });

  it("hides the choice when the patient has no entry to use", async () => {
    renderSheet();

    await waitFor(() => expect(api.shareableEvents).toHaveBeenCalled());
    expect(screen.queryByLabelText(/Use one of the patient's timeline entries/)).not.toBeInTheDocument();
  });

  it("explains a conflict and stays open, instead of closing as if it had worked", async () => {
    communicate.mockRejectedValue(new ApiError(409, "This result has already been communicated"));
    const onDone = vi.fn();
    renderSheet({ onDone });

    fireEvent.click(send());

    expect(await screen.findByRole("alert")).toHaveTextContent("already told");
    expect(onDone).not.toHaveBeenCalled();
    expect(send()).toBeEnabled();
  });

  it("says so when sending fails for any other reason", async () => {
    communicate.mockRejectedValue(new Error("500"));
    renderSheet();

    fireEvent.click(send());

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not send. Try again.");
  });

  it("starts each result from its own suggestion, not the last one's text", () => {
    const { rerenderWith } = renderSheet();
    fireEvent.change(messageBox(), { target: { value: "Something I typed" } });

    rerenderWith(review({ id: "r-2", result: { kind: "lab", test_name: "sodium", value: 120, unit: "mmol/L", taken_at: "2026-10-10T08:00:00" } }));

    expect(messageBox().value).toContain("result for Sodium: 120 mmol/L");
  });

  it("moves the suggestion to the new language while it is still the suggestion", async () => {
    renderSheet();
    expect(messageBox().value).toContain("Hello, we reviewed your result for Potassium");

    fireEvent.click(screen.getByRole("button", { name: "to-es" }));

    await waitFor(() =>
      expect((screen.getByLabelText("Mensaje para el paciente") as HTMLTextAreaElement).value).toContain(
        "revisamos su resultado de Potasio: 6.2 mEq/L",
      ),
    );
  });

  it("never replaces the clinician's own words when the language changes", async () => {
    renderSheet();
    fireEvent.change(messageBox(), { target: { value: "My own words" } });

    fireEvent.click(screen.getByRole("button", { name: "to-es" }));

    await screen.findByLabelText("Mensaje para el paciente");
    expect((screen.getByLabelText("Mensaje para el paciente") as HTMLTextAreaElement).value).toBe("My own words");
  });

  it("cancelling closes it without sending anything", () => {
    const onClose = vi.fn();
    renderSheet({ onClose });

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalled();
    expect(communicate).not.toHaveBeenCalled();
  });

  it("speaks Spanish", () => {
    localStorage.setItem("cac_lang", "es");
    renderSheet();

    return waitFor(() => {
      expect(screen.getAllByText("Avisar al paciente").length).toBeGreaterThan(0);
      expect((screen.getByLabelText("Mensaje para el paciente") as HTMLTextAreaElement).value).toContain(
        "revisamos su resultado de Potasio: 6.2 mEq/L",
      );
    });
  });
});
