import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AnswerRating from "@/components/answer-rating";
import { api, type Rating } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

const saved = (over: Partial<Rating> = {}): Rating => ({
  value: "up",
  reason: null,
  comment: "",
  updated_at: "2026-10-18T12:00:00",
  ...over,
});

function renderRating(initial: Rating | null = null) {
  render(
    <LanguageProvider>
      <AnswerRating consultationId="C1" initial={initial} />
    </LanguageProvider>,
  );
}

describe("AnswerRating", () => {
  let rate: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    rate = vi.spyOn(api, "rateConsultation").mockResolvedValue(saved());
  });

  afterEach(() => vi.restoreAllMocks());

  it("saves a useful rating on the click and confirms it", async () => {
    renderRating();

    fireEvent.click(screen.getByRole("button", { name: /Useful/ }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Thanks, your rating was saved."));
    expect(rate).toHaveBeenCalledWith("C1", { value: "up" });
  });

  it("asks why before saving a not-useful rating, and sends reason and comment", async () => {
    rate.mockResolvedValue(saved({ value: "down", reason: "unsafe", comment: "dose" }));
    renderRating();

    fireEvent.click(screen.getByRole("button", { name: /Not useful/ }));
    expect(rate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("radio", { name: "Unsafe" }));
    fireEvent.change(screen.getByLabelText(/Comment/), { target: { value: "  dose  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(rate).toHaveBeenCalledWith("C1", { value: "down", reason: "unsafe", comment: "dose" }));
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
  });

  it("lets the reason be skipped", async () => {
    rate.mockResolvedValue(saved({ value: "down" }));
    renderRating();

    fireEvent.click(screen.getByRole("button", { name: /Not useful/ }));
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(rate).toHaveBeenCalledWith("C1", { value: "down", reason: undefined, comment: "" }));
  });

  it("marks the chosen reason and caps the comment at 500 characters", () => {
    renderRating();
    fireEvent.click(screen.getByRole("button", { name: /Not useful/ }));

    fireEvent.click(screen.getByRole("radio", { name: "Incomplete" }));

    expect(screen.getByRole("radio", { name: "Incomplete" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Unsafe" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByLabelText(/Comment/)).toHaveAttribute("maxlength", "500");
  });

  it("cancelling goes back without saving anything", () => {
    renderRating();
    fireEvent.click(screen.getByRole("button", { name: /Not useful/ }));

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(rate).not.toHaveBeenCalled();
    expect(screen.getByText("Was this answer useful?")).toBeInTheDocument();
  });

  it("lets a saved rating be changed", async () => {
    renderRating(saved());

    fireEvent.click(screen.getByRole("button", { name: "Change" }));

    expect(screen.getByRole("button", { name: /Useful/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Not useful/ })).toBeInTheDocument();
  });

  it("says so when saving fails and keeps the buttons usable", async () => {
    rate.mockRejectedValue(new Error("500"));
    renderRating();

    fireEvent.click(screen.getByRole("button", { name: /Useful/ }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Could not save your rating"));
    expect(screen.getByRole("button", { name: /Useful/ })).toBeEnabled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
