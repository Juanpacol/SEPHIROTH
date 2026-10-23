import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AccentTitle from "@/components/landing/accent-title";

describe("AccentTitle", () => {
  it("reads as one sentence, with a space between the words", () => {
    render(<AccentTitle text="An answer, taken apart" />);

    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("An answer, taken apart");
  });

  it("sets the last words apart and only those", () => {
    const { container } = render(<AccentTitle text="An answer, taken apart" accentWords={2} />);

    const accented = Array.from(container.querySelectorAll("[data-accent]")).map((el) => el.textContent);
    expect(accented).toEqual(["taken", "apart"]);
  });

  it("is in the display face, in capitals", () => {
    render(<AccentTitle text="Two words" />);

    const className = screen.getByRole("heading").className;
    expect(className).toContain("font-display");
    expect(className).toContain("uppercase");
  });
});
