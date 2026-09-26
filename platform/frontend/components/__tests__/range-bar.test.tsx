import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import RangeBar from "@/components/dashboard/range-bar";

describe("RangeBar", () => {
  it("states value and threshold in text beside the mark", () => {
    render(
      <RangeBar
        factor={{ test: "potassium", value: 6.8, comparator: ">", threshold: 5.5, unit: "mEq/L" }}
        text="Potasio 6.8 mEq/L · umbral > 5.5"
      />
    );
    expect(screen.getByText("Potasio 6.8 mEq/L · umbral > 5.5")).toBeInTheDocument();
  });

  it("marks a firing value in danger and a non-firing one neutrally", () => {
    const { container, rerender } = render(
      <RangeBar factor={{ test: "ef", value: 30, comparator: "<", threshold: 40, unit: "%" }} text="EF" />
    );
    expect(container.querySelector(".bg-danger")).not.toBeNull();
    rerender(<RangeBar factor={{ test: "bp_diastolic", value: 95, comparator: "≥", threshold: 100, unit: "mmHg" }} text="PA" />);
    expect(container.querySelector(".bg-danger")).toBeNull();
    expect(container.querySelector(".bg-ink\\/50")).not.toBeNull();
  });
});
