import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import HeroTriptych from "@/components/landing/hero-triptych";
import { LANDING_FEATURES } from "@/lib/landing-features";
import EN from "@/lib/i18n/dictionaries.en";
import { LanguageProvider } from "@/lib/language";

const renderHero = () =>
  render(
    <LanguageProvider>
      <HeroTriptych />
    </LanguageProvider>,
  );

describe("HeroTriptych", () => {
  it("shows the Ask, Verify and Share cells of the feature grid, with their own words", () => {
    const { container } = renderHero();

    const panels = Array.from(container.querySelectorAll("[data-panel]"));
    expect(panels.map((p) => p.getAttribute("data-panel"))).toEqual(["ask", "verify", "share"]);
    for (const id of ["ask", "verify", "share"]) {
      const feature = LANDING_FEATURES.find((f) => f.id === id)!;
      expect(container.querySelector(`[data-panel='${id}']`)).toHaveTextContent(
        EN[feature.titleKey as keyof typeof EN],
      );
    }
  });

  it("has one headline, and sets its last three words apart", () => {
    renderHero();

    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent("Give every clinician back the minutes lost to lookups");
    const words = h1.querySelectorAll("span");
    expect(words[words.length - 1].className).toContain("text-[#b6cfff]");
    expect(words[words.length - 3].className).toContain("text-[#b6cfff]");
    expect(words[words.length - 4].className).not.toContain("text-[#b6cfff]");
  });

  it("offers the way in and the way to the explanation", () => {
    renderHero();

    expect(screen.getByRole("link", { name: /Open the app/ })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "See how it works" })).toHaveAttribute("href", "#how-it-works");
  });

  it("focusing a panel opens it, for the keyboard", () => {
    const { container } = renderHero();
    const verify = container.querySelector("[data-panel='verify']")!;

    fireEvent.focus(verify);

    return new Promise<void>((resolve) =>
      setTimeout(() => {
        expect(verify).toHaveAttribute("data-open", "true");
        resolve();
      }, 30),
    );
  });
});
