import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TrustCarousel from "@/components/landing/trust-carousel";
import { LanguageProvider } from "@/lib/language";

describe("TrustCarousel", () => {
  it("holds the three safeguards, each with its demonstration", () => {
    render(
      <LanguageProvider>
        <TrustCarousel />
      </LanguageProvider>,
    );

    const cards = screen.getAllByRole("listitem");
    expect(cards).toHaveLength(3);
    expect(within(cards[0]).getByRole("heading")).toHaveTextContent("No made-up citations");
    expect(within(cards[1]).getByRole("heading")).toHaveTextContent(
      "Every sentence, checked against real evidence",
    );
    expect(within(cards[2]).getByRole("heading")).toHaveTextContent("When it's not sure, it says so");
  });

  it("has arrows for a mouse, the first disabled while the row is at its start", () => {
    render(
      <LanguageProvider>
        <TrustCarousel />
      </LanguageProvider>,
    );

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
  });
});
