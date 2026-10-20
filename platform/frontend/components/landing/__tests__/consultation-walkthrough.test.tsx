import { readFileSync } from "node:fs";
import path from "node:path";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ConsultationWalkthrough from "@/components/landing/consultation-walkthrough";
import { WALKTHROUGH_STAGES } from "@/lib/landing-content";
import { LanguageProvider } from "@/lib/language";

function stubMotion({ reduce }: { reduce: boolean }) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? reduce : false,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

const panels = () => screen.getAllByRole("tabpanel", { hidden: true });
const shown = () => panels().filter((p) => !p.className.includes("invisible"));

function renderWalkthrough() {
  return render(
    <LanguageProvider>
      <ConsultationWalkthrough />
    </LanguageProvider>,
  );
}

describe("ConsultationWalkthrough", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("keeps every stage in the page and shows one, so the panel is as tall as the tallest", () => {
    stubMotion({ reduce: true });
    renderWalkthrough();

    expect(panels()).toHaveLength(WALKTHROUGH_STAGES.length);
    expect(shown()).toHaveLength(1);
    // Every panel shares one grid cell: that is what makes the height constant.
    for (const panel of panels()) expect(panel.className).toContain("col-start-1 row-start-1");
    expect(panels()[0].parentElement?.className).toContain("grid");
  });

  it("moves to the stage whose tab is clicked, and nothing else changes size", () => {
    stubMotion({ reduce: true });
    renderWalkthrough();

    fireEvent.click(screen.getAllByRole("tab")[2]);

    expect(shown()).toEqual([panels()[2]]);
    expect(panels()).toHaveLength(WALKTHROUGH_STAGES.length);
  });

  it("only the shown stage is announced", () => {
    stubMotion({ reduce: true });
    renderWalkthrough();

    expect(panels().map((p) => p.getAttribute("aria-live"))).toEqual(["polite", "off", "off", "off", "off"]);
  });

  it("advances by itself, and the page structure stays the same while it does", () => {
    stubMotion({ reduce: false });
    renderWalkthrough();
    const before = panels().length;

    act(() => {
      vi.advanceTimersByTime(2200 * 2 + 100);
    });

    expect(shown()).toEqual([panels()[2]]);
    expect(panels()).toHaveLength(before);
  });

  it("does not advance by itself under reduced motion", () => {
    stubMotion({ reduce: true });
    renderWalkthrough();

    act(() => {
      vi.advanceTimersByTime(10_000);
    });

    expect(shown()).toEqual([panels()[0]]);
  });

  it("no longer measures a panel height or animates one", () => {
    const source = readFileSync(path.join(__dirname, "..", "consultation-walkthrough.tsx"), "utf8");

    expect(source).not.toMatch(/scrollHeight|setPanelHeight|panelHeight|transition-\[height\]/);
  });
});
