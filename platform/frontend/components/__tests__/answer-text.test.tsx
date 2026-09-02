import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import AnswerText, { toBlocks } from "@/components/copilot/answer-text";

describe("toBlocks", () => {
  it("joins wrapped prose lines into one paragraph", () => {
    expect(toBlocks("First line\nstill the same sentence.")).toEqual([
      { type: "paragraph", lines: ["First line", "still the same sentence."] },
    ]);
  });

  it("starts a new paragraph on a blank line", () => {
    const blocks = toBlocks("One.\n\nTwo.");
    expect(blocks.map((b) => b.type)).toEqual(["paragraph", "paragraph"]);
  });

  it("groups consecutive bullets into a single list", () => {
    const blocks = toBlocks("Options:\n- thiazide\n- ACE inhibitor\n* ARB");
    expect(blocks).toEqual([
      { type: "paragraph", lines: ["Options:"] },
      { type: "list", lines: ["thiazide", "ACE inhibitor", "ARB"] },
    ]);
  });
});

describe("AnswerText", () => {
  it("renders bold runs as emphasis, not literal asterisks", () => {
    // The whole point: `whitespace-pre-wrap` used to print the asterisks.
    render(<AnswerText answer="Start a **thiazide diuretic** first." />);

    expect(screen.getByText("thiazide diuretic").tagName).toBe("STRONG");
    expect(screen.queryByText(/\*\*/)).toBeNull();
  });

  it("renders bullets as list items", () => {
    // Braces, not a plain attribute: "\n" inside JSX quotes is a literal
    // backslash-n, not a newline.
    render(<AnswerText answer={"- ACE inhibitor\n- ARB"} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("leaves unsupported markdown verbatim rather than interpreting it", () => {
    // Anything outside the prompted subset must not be silently swallowed.
    render(<AnswerText answer="See [ACC/AHA, 2023](http://x) and _italics_." />);
    expect(screen.getByText(/\[ACC\/AHA, 2023\]\(http:\/\/x\) and _italics_\./)).toBeTruthy();
  });

  it("renders an empty answer without crashing", () => {
    const { container } = render(<AnswerText answer="" />);
    expect(container.textContent).toBe("");
  });
});
