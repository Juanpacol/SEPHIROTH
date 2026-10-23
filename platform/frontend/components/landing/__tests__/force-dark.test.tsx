import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import ForceDark from "@/components/landing/force-dark";

describe("ForceDark", () => {
  afterEach(() => document.documentElement.classList.remove("dark"));

  it("makes the page dark while it is on screen", () => {
    render(<ForceDark />);

    expect(document.documentElement).toHaveClass("dark");
  });

  it("takes the dark away again on leaving when the reader's theme was light", () => {
    const { unmount } = render(<ForceDark />);

    unmount();

    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("leaves it on when the reader's theme was dark to begin with", () => {
    document.documentElement.classList.add("dark");
    const { unmount } = render(<ForceDark />);

    unmount();

    expect(document.documentElement).toHaveClass("dark");
  });
});
