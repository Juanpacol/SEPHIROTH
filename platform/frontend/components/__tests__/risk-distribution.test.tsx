import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import RiskDistribution from "@/components/dashboard/risk-distribution";
import { LanguageProvider } from "@/lib/language";

function renderBar(props: { critical: number; moderate: number; stable: number }) {
  localStorage.setItem("cac_lang", "es");
  return render(
    <LanguageProvider>
      <RiskDistribution {...props} />
    </LanguageProvider>
  );
}

describe("RiskDistribution", () => {
  afterEach(() => localStorage.removeItem("cac_lang"));

  it("names, counts and proportions every state as text, not only colour", () => {
    renderBar({ critical: 2, moderate: 3, stable: 5 });
    expect(screen.getByText("Críticos")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("aria-label", "Críticos 2, Moderados 3, Estables 5");
  });

  it("sizes segments by share and skips empty ones", () => {
    const { container } = renderBar({ critical: 1, moderate: 0, stable: 3 });
    const segments = container.querySelectorAll('[role="img"] > div');
    expect(segments).toHaveLength(2);
    expect((segments[0] as HTMLElement).style.width).toBe("25%");
  });

  it("says so when there is nobody to classify", () => {
    renderBar({ critical: 0, moderate: 0, stable: 0 });
    expect(screen.getByText("Todavía no hay pacientes para clasificar.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
