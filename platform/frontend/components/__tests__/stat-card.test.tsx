import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import StatCard from "@/components/stat-card";

describe("StatCard", () => {
  it("shows the scale next to the value and a legend under it", () => {
    render(<StatCard label="Puntaje de prioridad máxima" value={3} suffix="de 3" hint="1 bajo · 2 moderado · 3 alto" />);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("de 3")).toBeInTheDocument();
    expect(screen.getByText("1 bajo · 2 moderado · 3 alto")).toBeInTheDocument();
  });

  it("renders just the number when no scale is given", () => {
    const { container } = render(<StatCard label="Críticos" value={1} />);
    expect(container.textContent).toBe("Críticos1");
  });

  it("hides the scale when there is no value", () => {
    render(<StatCard label="Puntaje" value={null} suffix="de 3" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("de 3")).not.toBeInTheDocument();
  });
});
