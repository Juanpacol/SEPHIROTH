import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AnalysisDemo from "@/components/landing/analysis-demo";
import { DEMO_STUDIES } from "@/lib/imaging-demo";
import { LanguageProvider } from "@/lib/language";

const renderDemo = () =>
  render(
    <LanguageProvider>
      <AnalysisDemo />
    </LanguageProvider>,
  );
const panels = () => screen.getAllByRole("tabpanel", { hidden: true });

describe("AnalysisDemo", () => {
  it("has a tab per study, the first selected, and every panel in the page", () => {
    renderDemo();

    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(DEMO_STUDIES.length);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(panels()).toHaveLength(DEMO_STUDIES.length);
    // All in one grid cell, so the section is as tall as the tallest.
    for (const panel of panels()) expect(panel.className).toContain("col-start-1 row-start-1");
  });

  it("shows one panel at a time and hides the others from assistive technology", () => {
    renderDemo();

    expect(panels().map((p) => p.getAttribute("aria-hidden"))).toEqual(["false", "true", "true", "true"]);
    fireEvent.click(screen.getAllByRole("tab")[2]);
    expect(panels().map((p) => p.getAttribute("aria-hidden"))).toEqual(["true", "true", "false", "true"]);
    expect(screen.getAllByRole("tab")[2]).toHaveAttribute("aria-selected", "true");
  });

  it("moves with the arrow keys, wraps around, and keeps one tab in the tab order", () => {
    renderDemo();
    const tabs = screen.getAllByRole("tab");

    fireEvent.keyDown(tabs[0], { key: "ArrowLeft" });
    expect(tabs[3]).toHaveAttribute("aria-selected", "true");
    expect(tabs[3]).toHaveFocus();
    fireEvent.keyDown(tabs[3], { key: "ArrowRight" });
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs[0], { key: "End" });
    expect(tabs[3]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabs[3], { key: "Home" });
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs.map((t) => t.getAttribute("tabindex"))).toEqual(["0", "-1", "-1", "-1"]);
  });

  it("each panel is labelled by its tab, and says the text is an example, not a diagnosis", () => {
    renderDemo();

    for (const study of DEMO_STUDIES) {
      const panel = document.getElementById(`demo-panel-${study.id}`)!;
      expect(panel.getAttribute("aria-labelledby")).toBe(`demo-tab-${study.id}`);
      expect(panel.textContent).toContain(study.description.slice(0, 40));
      expect(panel.textContent).toMatch(/not a diagnosis/i);
    }
  });
});
