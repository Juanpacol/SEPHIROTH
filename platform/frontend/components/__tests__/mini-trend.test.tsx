import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MiniTrend from "@/components/dashboard/mini-trend";

describe("MiniTrend", () => {
  it("draws nothing for a single reading", () => {
    const { container } = render(<MiniTrend values={[5.1]} label="t" />);
    expect(container.querySelector("svg")).toBeNull();
  });

  it("draws oldest to newest with an accessible description", () => {
    render(<MiniTrend values={[4.4, 5.2, 6.8]} lastTone="danger" label="de 4.4 a 6.8" />);
    const svg = screen.getByRole("img", { name: "de 4.4 a 6.8" });
    const points = svg.querySelector("polyline")!.getAttribute("points")!.split(" ");
    expect(points).toHaveLength(3);
    const ys = points.map((p) => Number(p.split(",")[1]));
    expect(ys[0]).toBeGreaterThan(ys[2]);
    expect(svg.querySelector("circle")).toHaveClass("fill-danger");
  });
});
