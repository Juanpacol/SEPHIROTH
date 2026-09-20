import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TimelineEventSheet from "@/components/patients/timeline-event-sheet";
import { type TimelineEvent } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

function renderSheet(event: TimelineEvent | null, onClose = vi.fn()) {
  return render(
    <LanguageProvider>
      <TimelineEventSheet event={event} onClose={onClose} />
    </LanguageProvider>
  );
}

const EVENT: TimelineEvent = {
  date: "2026-05-01",
  type: "diagnosis",
  title: "Type 2 diabetes",
  detail: "Confirmed by fasting glucose and A1C.",
  ai_generated: true,
};

describe("TimelineEventSheet", () => {
  it("renders nothing when event is null", () => {
    renderSheet(null);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the event's date, title and detail", () => {
    renderSheet(EVENT);
    expect(screen.getByText(EVENT.date)).toBeInTheDocument();
    expect(screen.getByText(EVENT.title)).toBeInTheDocument();
    expect(screen.getByText(EVENT.detail)).toBeInTheDocument();
  });

  it("shows the AI badge when ai_generated is true, hides it otherwise", () => {
    const { unmount } = renderSheet(EVENT);
    expect(screen.getByText("AI-extracted")).toBeInTheDocument();
    unmount();

    renderSheet({ ...EVENT, ai_generated: false });
    expect(screen.queryByText("AI-extracted")).not.toBeInTheDocument();
  });

  it("shows the empty-detail copy when detail is empty", () => {
    renderSheet({ ...EVENT, detail: "" });
    expect(
      screen.getByText("No further description was recorded for this event.")
    ).toBeInTheDocument();
  });

  it("falls back to the raw type string for an unknown type", () => {
    renderSheet({ ...EVENT, type: "unheard-of" });
    expect(screen.getByText("unheard-of")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("patientDetail.timeline.type.");
  });

  it("calls onClose once when the close button is clicked", () => {
    const onClose = vi.fn();
    renderSheet(EVENT, onClose);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
