import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TimelineList, { TIMELINE_COLLAPSED_COUNT } from "@/components/patients/timeline-list";
import { type TimelineEvent } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

/** Oldest first, like the API: "Event 1" is the oldest. */
function makeEvents(count: number): TimelineEvent[] {
  return Array.from({ length: count }, (_, i) => ({
    date: `2026-01-${String(i + 1).padStart(2, "0")}`,
    type: "event",
    title: `Event ${i + 1}`,
    detail: `Detail ${i + 1}`,
  }));
}

function renderList(events: TimelineEvent[], onSelect = vi.fn()) {
  render(
    <LanguageProvider>
      <TimelineList events={events} onSelect={onSelect} />
    </LanguageProvider>,
  );
  return onSelect;
}

const titles = () => screen.getAllByRole("listitem").map((li) => li.querySelector(".font-semibold")?.textContent);

describe("TimelineList", () => {
  it("shows only the most recent events, still oldest-to-newest", () => {
    renderList(makeEvents(12));
    expect(titles()).toEqual(["Event 8", "Event 9", "Event 10", "Event 11", "Event 12"]);
    expect(TIMELINE_COLLAPSED_COUNT).toBe(5);
  });

  it("tells how many earlier events are hidden", () => {
    renderList(makeEvents(12));
    expect(screen.getByRole("button", { name: "Show 7 earlier events" })).toBeInTheDocument();
  });

  it("uses the singular when exactly one event is hidden", () => {
    renderList(makeEvents(6));
    expect(screen.getByRole("button", { name: "Show 1 earlier event" })).toBeInTheDocument();
  });

  it("expands to the full history in place, and folds back", () => {
    renderList(makeEvents(12));
    const toggle = screen.getByRole("button", { name: "Show 7 earlier events" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(titles()).toHaveLength(12);
    expect(titles()[0]).toBe("Event 1");
    expect(titles()[11]).toBe("Event 12");
    const less = screen.getByRole("button", { name: "Show less" });
    expect(less).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(less);
    expect(titles()).toEqual(["Event 8", "Event 9", "Event 10", "Event 11", "Event 12"]);
    expect(screen.getByRole("button", { name: "Show 7 earlier events" })).toBeInTheDocument();
  });

  it("links the toggle to the list it controls", () => {
    renderList(makeEvents(8));
    const toggle = screen.getByRole("button", { name: "Show 3 earlier events" });
    expect(document.getElementById(toggle.getAttribute("aria-controls")!)).toBe(screen.getByRole("list"));
  });

  it("shows no toggle at the threshold or below", () => {
    renderList(makeEvents(TIMELINE_COLLAPSED_COUNT));
    expect(titles()).toHaveLength(TIMELINE_COLLAPSED_COUNT);
    expect(screen.queryByRole("button", { name: /earlier|less/i })).not.toBeInTheDocument();
  });

  it("renders an empty list without a toggle", () => {
    renderList([]);
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("still opens an event's detail from the folded and the expanded list", () => {
    const events = makeEvents(8);
    const onSelect = renderList(events);

    fireEvent.click(screen.getByText("Event 8"));
    expect(onSelect).toHaveBeenLastCalledWith(events[7]);

    fireEvent.click(screen.getByRole("button", { name: "Show 3 earlier events" }));
    fireEvent.click(screen.getByText("Event 1"));
    expect(onSelect).toHaveBeenLastCalledWith(events[0]);
  });

  it("keeps a new event in the folded view without expanding", () => {
    const events = makeEvents(8);
    const { rerender } = render(
      <LanguageProvider>
        <TimelineList events={events} onSelect={vi.fn()} />
      </LanguageProvider>,
    );
    rerender(
      <LanguageProvider>
        <TimelineList
          events={[...events, { date: "2026-02-01", type: "note", title: "Brand new note", detail: "" }]}
          onSelect={vi.fn()}
        />
      </LanguageProvider>,
    );
    expect(titles()).toEqual(["Event 5", "Event 6", "Event 7", "Event 8", "Brand new note"]);
    expect(screen.getByRole("button", { name: "Show 4 earlier events" })).toBeInTheDocument();
  });
});
