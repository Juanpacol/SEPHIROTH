import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import RuleSummaryChart from "@/components/dashboard/rule-summary-chart";
import type { DashboardRuleSummary } from "@/lib/api";
import { LanguageProvider } from "@/lib/language";

function rule(code: string, label: string, count: number, severity: "high" | "medium" = "high") {
  return {
    rule_code: code,
    label,
    severity,
    count,
    patients: Array.from({ length: count }, (_, i) => ({
      id: `${code}-${i}`,
      name: `Paciente ${code} ${i}`,
      risk_level: "high" as const,
    })),
  };
}

function renderChart(summary: DashboardRuleSummary) {
  localStorage.setItem("cac_lang", "es");
  return render(
    <LanguageProvider>
      <RuleSummaryChart summary={summary} />
    </LanguageProvider>
  );
}

describe("RuleSummaryChart", () => {
  afterEach(() => localStorage.removeItem("cac_lang"));

  it("draws one translated, counted bar per problem, sized against the largest", () => {
    const { container } = renderChart({
      total_patients: 6,
      rules: [rule("hyperkalemia", "Hyperkalemia", 4), rule("drug_interaction", "Interaction", 2, "medium")],
    });
    expect(screen.getByText("Potasio alto (hiperpotasemia)")).toBeInTheDocument();
    expect(screen.getByText("Interacción de medicamentos")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    const fills = container.querySelectorAll<HTMLElement>(".bg-danger, .bg-warning");
    expect(fills[0].style.width).toBe("100%");
    expect(fills[1].style.width).toBe("50%");
  });

  it("expands a bar into its patients, each linking to the chart", () => {
    renderChart({ total_patients: 3, rules: [rule("hyperkalemia", "Hyperkalemia", 2)] });
    const bar = screen.getByRole("button", { name: /hiperpotasemia\): 2 pacientes/i });
    expect(bar).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();

    fireEvent.click(bar);
    expect(bar).toHaveAttribute("aria-expanded", "true");
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "/patients/hyperkalemia-0");
    expect(within(links[0]).getByText("Riesgo alto")).toBeInTheDocument();
  });

  it("shows six bars first and offers the rest", () => {
    renderChart({
      total_patients: 20,
      rules: Array.from({ length: 8 }, (_, i) => rule(`rule_${i}`, `Rule ${i}`, 8 - i)),
    });
    expect(screen.getAllByRole("button", { expanded: false })).toHaveLength(6);
    fireEvent.click(screen.getByText("Ver 2 problemas más"));
    expect(screen.getAllByRole("button", { expanded: false })).toHaveLength(8);
  });

  it("says so when nobody has an active problem", () => {
    renderChart({ total_patients: 4, rules: [] });
    expect(screen.getByText("Ningún paciente tiene problemas activos.")).toBeInTheDocument();
  });
});
