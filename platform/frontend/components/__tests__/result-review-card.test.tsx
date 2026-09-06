/** One result's card, and the guard it makes visible.
 *
 * The server refuses to close a result whose decision was "tell the patient"
 * until they have been told. This card disables the button and says why, so the
 * refusal is never a 409 arriving after somebody thought they were finished —
 * the same posture `tasks.py` takes with `completable_refusal`.
 *
 * The classification's reason is asserted to be on screen because a severity a
 * clinician cannot trace back to a threshold is one they have to take on faith,
 * and this one is arithmetic they can check in a second.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ResultReviewCard from "@/components/results/result-review-card";
import type { ResultReview } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

function review(overrides: Partial<ResultReview> = {}): ResultReview {
  return {
    id: "R1",
    result_type: "lab",
    result_id: "1",
    patient_id: "P1",
    patient_name: "Ana Gómez",
    status: "received",
    severity: "critical",
    classification_reason: "K+ > 5.5 mEq/L",
    disposition: null,
    note: "",
    reviewed_at: null,
    reviewed_by: null,
    share_id: null,
    task_id: "T1",
    closed_at: null,
    created_at: "2026-09-06T09:00:00",
    needs_communication: false,
    closable: false,
    result: {
      kind: "lab",
      test_name: "potassium",
      value: 6.2,
      unit: "mEq/L",
      reference_low: 3.5,
      reference_high: 5.0,
      taken_at: "2026-09-06T08:00:00",
    },
    ...overrides,
  };
}

function renderCard(overrides: Partial<ResultReview> = {}) {
  const handlers = {
    onReview: vi.fn(),
    onCommunicate: vi.fn(),
    onClose: vi.fn(),
    onReopen: vi.fn(),
  };
  render(
    <LanguageProvider>
      <ResultReviewCard review={review(overrides)} {...handlers} />
    </LanguageProvider>,
  );
  return handlers;
}

const closeButton = () => screen.getByRole("button", { name: /cerrar|close/i });

describe("ResultReviewCard", () => {
  it("shows the value, its range and why it was classified that way", () => {
    renderCard();

    expect(screen.getByText(/potassium: 6.2 mEq\/L \(3.5–5\)/)).toBeInTheDocument();
    expect(screen.getByText("K+ > 5.5 mEq/L")).toBeInTheDocument();
  });

  it("names the patient the result belongs to", () => {
    renderCard();
    expect(screen.getByText("Ana Gómez")).toBeInTheDocument();
  });

  it("offers the decision form only while nobody has decided", () => {
    renderCard();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("will not submit a non-normal decision without a reason", () => {
    const { onReview } = renderCard();

    fireEvent.click(screen.getByRole("button", { name: /registrar|record the decision/i }));

    expect(onReview).not.toHaveBeenCalled();
  });

  it("submits once a reason is written", () => {
    const { onReview } = renderCard();

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Suspendo el IECA" } });
    fireEvent.click(screen.getByRole("button", { name: /registrar|record the decision/i }));

    expect(onReview).toHaveBeenCalledWith({
      disposition: "action_taken",
      note: "Suspendo el IECA",
    });
  });

  it("lets a normal result through with no reason", () => {
    const { onReview } = renderCard({ severity: "normal", classification_reason: "Within range" });

    fireEvent.click(screen.getByRole("button", { name: /registrar|record the decision/i }));

    expect(onReview).toHaveBeenCalledWith({ disposition: "normal", note: "" });
  });

  it("disables Close while the patient has not been told", () => {
    renderCard({
      status: "reviewed",
      disposition: "needs_patient_contact",
      note: "Avisar",
      needs_communication: true,
      closable: false,
    });

    expect(closeButton()).toBeDisabled();
    expect(
      screen.getAllByText(/queda abierto hasta|stays open until/i).length,
    ).toBeGreaterThan(0);
  });

  it("offers the way to tell them", () => {
    const { onCommunicate } = renderCard({
      status: "reviewed",
      disposition: "needs_patient_contact",
      note: "Avisar",
      needs_communication: true,
      closable: false,
    });

    fireEvent.click(screen.getByRole("button", { name: /avisar al paciente|tell the patient/i }));

    expect(onCommunicate).toHaveBeenCalled();
  });

  it("enables Close once they have been told", () => {
    const { onClose } = renderCard({
      status: "communicated",
      disposition: "needs_patient_contact",
      note: "Avisar",
      share_id: "S1",
      needs_communication: false,
      closable: true,
    });

    fireEvent.click(closeButton());

    expect(onClose).toHaveBeenCalled();
  });

  it("enables Close directly for a decision that creates no obligation", () => {
    renderCard({
      status: "reviewed",
      disposition: "action_taken",
      note: "Hecho",
      closable: true,
    });

    expect(closeButton()).toBeEnabled();
  });

  it("shows the decision instead of the form once it is made", () => {
    renderCard({ status: "reviewed", disposition: "action_taken", note: "Suspendo el IECA" });

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByText("Suspendo el IECA")).toBeInTheDocument();
  });

  it("offers reopen on a closed result and no close button", () => {
    const { onReopen } = renderCard({
      status: "closed",
      disposition: "action_taken",
      note: "Hecho",
      closed_at: "2026-09-06T10:00:00",
      closable: false,
    });

    expect(screen.queryByRole("button", { name: /^cerrar$|^close$/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /reabrir|reopen/i }));
    expect(onReopen).toHaveBeenCalled();
  });

  it("renders an imaging result in its own shape", () => {
    renderCard({
      result_type: "imaging",
      severity: "abnormal",
      classification_reason: "Nódulo de 8mm",
      result: {
        kind: "imaging",
        modality: "TAC",
        body_part: "cráneo",
        study_date: "2026-09-06",
        finding_summary: "Nódulo de 8mm",
        severity: "review",
      },
    });

    expect(screen.getByText(/TAC cráneo — Nódulo de 8mm/)).toBeInTheDocument();
  });
});
