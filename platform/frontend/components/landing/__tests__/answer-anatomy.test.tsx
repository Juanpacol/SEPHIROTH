import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import AnswerAnatomy from "@/components/landing/answer-anatomy";
import { ANATOMY_STEPS } from "@/lib/landing-anatomy";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";
import { LanguageProvider } from "@/lib/language";

const renderAnatomy = () =>
  render(
    <LanguageProvider>
      <AnswerAnatomy />
    </LanguageProvider>,
  );
const step = (c: HTMLElement, id: string) => c.querySelector(`[data-step='${id}']`)!;
const part = (c: HTMLElement, id: string) => c.querySelector(`[data-part='${id}']`)!;

describe("AnswerAnatomy", () => {
  it("writes out all five steps, in order, always: nothing is behind a hover", () => {
    const { container } = renderAnatomy();

    expect(ANATOMY_STEPS.map((s) => s.id)).toEqual(["route", "write", "guard", "verify", "abstain"]);
    for (const s of ANATOMY_STEPS) {
      expect(step(container, s.id)).toHaveTextContent(EN[s.titleKey as keyof typeof EN]);
      expect(step(container, s.id)).toHaveTextContent(EN[s.bodyKey as keyof typeof EN]);
    }
  });

  it("starts on the first step, with its part of the answer lit and the others quiet", () => {
    const { container } = renderAnatomy();

    expect(step(container, "route")).toHaveAttribute("aria-pressed", "true");
    expect(part(container, "route")).toHaveAttribute("data-active", "true");
    expect(part(container, "guard")).toHaveAttribute("data-active", "false");
  });

  it("lights the part a step is about when the step is pointed at, focused or tapped", () => {
    const { container } = renderAnatomy();

    fireEvent.mouseEnter(step(container, "guard"));
    expect(part(container, "guard")).toHaveAttribute("data-active", "true");
    expect(part(container, "route")).toHaveAttribute("data-active", "false");

    fireEvent.focus(step(container, "verify"));
    expect(part(container, "verify")).toHaveAttribute("data-active", "true");

    fireEvent.click(step(container, "abstain"));
    expect(part(container, "abstain")).toHaveAttribute("data-active", "true");
    expect(step(container, "abstain")).toHaveAttribute("aria-pressed", "true");
    expect(step(container, "verify")).toHaveAttribute("aria-pressed", "false");
  });

  it("lights the step a part belongs to when the part is pointed at", () => {
    const { container } = renderAnatomy();

    fireEvent.mouseEnter(part(container, "write"));

    expect(step(container, "write")).toHaveAttribute("aria-pressed", "true");
  });

  it("shows the sample answer: one citation kept, one removed, one claim excluded, one part declined", () => {
    renderAnatomy();

    expect(screen.getByText(/ADA Standards of Care, 2024/)).toBeInTheDocument();
    expect(screen.getByText(/UpToDate Diabetes Review, 2023/)).toBeInTheDocument();
    expect(screen.getByText("removed: not in the evidence")).toBeInTheDocument();
    expect(screen.getByText("Excluded")).toBeInTheDocument();
    expect(screen.getByText(/so no answer is given/)).toBeInTheDocument();
  });

  it("every text it uses exists in both languages", () => {
    const keys = [
      ...ANATOMY_STEPS.flatMap((s) => [s.titleKey, s.bodyKey]),
      "marketing.anatomy.stepsLabel",
      "marketing.anatomy.card.label",
      "marketing.anatomy.card.answer",
      "marketing.anatomy.card.cite1",
      "marketing.anatomy.card.cite2",
      "marketing.anatomy.card.removed",
      "marketing.anatomy.card.excluded",
      "marketing.anatomy.card.abstain",
      "marketing.howItWorks.eyebrow",
      "marketing.howItWorks.title",
      "marketing.howItWorks.body",
    ];
    for (const key of keys) {
      expect((EN as Record<string, string>)[key], `en ${key}`).toBeTruthy();
      expect((ES as Record<string, string>)[key], `es ${key}`).toBeTruthy();
    }
  });
});
