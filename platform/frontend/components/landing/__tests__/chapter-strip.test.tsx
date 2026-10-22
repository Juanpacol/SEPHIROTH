import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ChapterStrip from "@/components/landing/chapter-strip";
import { LanguageProvider } from "@/lib/language";

const renderStrip = () =>
  render(
    <LanguageProvider>
      <ChapterStrip />
    </LanguageProvider>,
  );

describe("ChapterStrip", () => {
  it("lists the three specialists and then the four parts of the platform", () => {
    renderStrip();

    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.getAttribute("data-group"))).toEqual([
      "agent",
      "agent",
      "agent",
      "platform",
      "platform",
      "platform",
      "platform",
    ]);
    expect(tabs[0]).toHaveTextContent("Image Analysis");
    expect(tabs[2]).toHaveTextContent("Guidelines & Literature");
  });

  it("starts on the first chapter and shows another when it is chosen", () => {
    renderStrip();
    expect(screen.getAllByRole("tab")[0]).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent(/not a diagnosis/i);

    fireEvent.click(screen.getByRole("tab", { name: /Appointment scheduling/ }));

    expect(screen.getByRole("tabpanel")).toHaveTextContent(/double-booking/i);
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Platform");
  });

  it("moves along the row with the arrow keys, wrapping at the ends", () => {
    renderStrip();
    const tabs = screen.getAllByRole("tab");

    fireEvent.keyDown(tabs[0], { key: "ArrowLeft" });
    expect(screen.getAllByRole("tab")[6]).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(screen.getAllByRole("tab")[6], { key: "ArrowRight" });
    expect(screen.getAllByRole("tab")[0]).toHaveAttribute("aria-selected", "true");
  });

  it("only the chosen tab is in the tab order", () => {
    renderStrip();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.filter((t) => t.tabIndex === 0)).toHaveLength(1);
  });
});
