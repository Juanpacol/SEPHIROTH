/** The drafting panel, and the two promises it makes on screen.
 *
 * The draft appears *beside* the note and is applied by a button, never written
 * into the record by arriving. That is the UI half of ADR-016.
 *
 * And a degraded draft is never dressed up as a model's work. When there is no
 * model the panel gets the clinician's own text back under headings, and saying
 * "drafted by qwen2.5" over it would be a small lie about the provenance of
 * clinical content.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NoteDraftPanel from "@/components/encounters/note-draft-panel";
import type { NoteDraft } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const draftEncounterNote = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { ...actual.api, draftEncounterNote: (...args: unknown[]) => draftEncounterNote(...args) } };
});

function draft(overrides: Partial<NoteDraft> = {}): NoteDraft {
  return {
    source: "llm",
    model: "qwen2.5:14b",
    subjective: "Tres días de cefalea.",
    objective: "PA 210/120.",
    assessment: "",
    plan: "Losartán 50mg.",
    ...overrides,
  };
}

function renderPanel(onApply = vi.fn()) {
  render(
    <LanguageProvider>
      <NoteDraftPanel encounterId="E1" specialty="general" onApply={onApply} />
    </LanguageProvider>,
  );
  return onApply;
}

function requestDraft() {
  fireEvent.change(screen.getByRole("textbox"), {
    target: { value: "cefalea tres días PA 210/120" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: /ordenar en secciones|organise into sections/i }),
  );
}

describe("NoteDraftPanel", () => {
  beforeEach(() => {
    draftEncounterNote.mockReset();
  });

  it("does not call the model until the clinician asks", () => {
    renderPanel();
    expect(draftEncounterNote).not.toHaveBeenCalled();
  });

  it("cannot be asked for a draft of nothing", () => {
    renderPanel();
    expect(
      screen.getByRole("button", { name: /ordenar en secciones|organise into sections/i }),
    ).toBeDisabled();
  });

  it("shows the draft without applying it", async () => {
    draftEncounterNote.mockResolvedValue(draft());
    const onApply = renderPanel();

    requestDraft();

    await waitFor(() => expect(screen.getByText("Tres días de cefalea.")).toBeInTheDocument());
    expect(onApply).not.toHaveBeenCalled();
  });

  it("applies only when the clinician presses apply", async () => {
    draftEncounterNote.mockResolvedValue(draft());
    const onApply = renderPanel();

    requestDraft();
    await waitFor(() => screen.getByText("Tres días de cefalea."));
    fireEvent.click(screen.getByRole("button", { name: /aplicar a la nota|apply to the note/i }));

    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ source: "llm" }));
  });

  it("names the model that drafted", async () => {
    draftEncounterNote.mockResolvedValue(draft());
    renderPanel();

    requestDraft();

    await waitFor(() => expect(screen.getByText(/qwen2\.5:14b/)).toBeInTheDocument());
  });

  it("says plainly when there was no model, instead of crediting one", async () => {
    draftEncounterNote.mockResolvedValue(
      draft({ source: "template", model: null, objective: "", plan: "" }),
    );
    renderPanel();

    requestDraft();

    await waitFor(() =>
      expect(screen.getByText(/no hay modelo disponible|no model available/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/qwen2\.5/)).not.toBeInTheDocument();
  });

  it("marks the sections the model wrote rather than reorganised", async () => {
    draftEncounterNote.mockResolvedValue(
      draft({ assessment: "Hipertensión arterial", added_content: ["assessment"] }),
    );
    renderPanel();

    requestDraft();

    await waitFor(() =>
      expect(
        screen.getByText(/no está en lo que escribiste|not in what you wrote/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/revisar|check/i)).toBeInTheDocument();
  });

  it("marks nothing when the model only reorganised", async () => {
    draftEncounterNote.mockResolvedValue(draft({ added_content: [] }));
    renderPanel();

    requestDraft();

    await waitFor(() => screen.getByText("Tres días de cefalea."));
    expect(
      screen.queryByText(/no está en lo que escribiste|not in what you wrote/i),
    ).not.toBeInTheDocument();
  });

  it("surfaces a failure instead of pretending it drafted", async () => {
    draftEncounterNote.mockRejectedValue(new Error("409 encounter is signed"));
    renderPanel();

    requestDraft();

    await waitFor(() => expect(screen.getByText(/409 encounter is signed/)).toBeInTheDocument());
  });
});
