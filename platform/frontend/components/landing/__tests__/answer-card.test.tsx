import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AnswerCard from "@/components/landing/answer-card";
import { ANSWER_EXAMPLES } from "@/lib/landing-answers";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";
import { LanguageProvider } from "@/lib/language";

function stubMotion(reduce: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: q.includes("prefers-reduced-motion") ? reduce : false,
    addEventListener() {},
    removeEventListener() {},
  }));
}
const renderCard = () =>
  render(
    <LanguageProvider>
      <AnswerCard />
    </LanguageProvider>,
  );
const selected = () => screen.getAllByRole("tab").find((t) => t.getAttribute("aria-selected") === "true")!;

describe("AnswerCard", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows an answer the way the product gives it: question, specialist, sources, claim checks, outcome", () => {
    stubMotion(true);
    renderCard();
    const panel = screen.getByRole("tabpanel");

    expect(panel).toHaveTextContent("What A1C goal is appropriate for a 62-year-old with type 2 diabetes?");
    expect(panel).toHaveTextContent("Guidelines & Literature");
    expect(panel).toHaveTextContent("[ADA Standards of Care, 2024]");
    expect(panel).toHaveTextContent("Confirmed");
    expect(panel).toHaveTextContent("Answered · 2 of 2 claims supported");
  });

  it("says it is an example", () => {
    stubMotion(true);
    renderCard();

    expect(screen.getByText("Example answer")).toBeInTheDocument();
  });

  it("moves on to the next example by itself, and wraps round", () => {
    stubMotion(false);
    renderCard();
    act(() => vi.advanceTimersByTime(0));
    expect(selected()).toHaveTextContent("Guideline");

    act(() => vi.advanceTimersByTime(8000));
    expect(selected()).toHaveTextContent("Medication");
    act(() => vi.advanceTimersByTime(8000));
    expect(selected()).toHaveTextContent("Declines");
    act(() => vi.advanceTimersByTime(8000));
    expect(selected()).toHaveTextContent("Guideline");
  });

  it("the third example shows the product declining to guess", () => {
    stubMotion(true);
    renderCard();

    fireEvent.click(screen.getByRole("tab", { name: "Declines" }));

    const panel = screen.getByRole("tabpanel");
    expect(panel).toHaveTextContent("declines to answer instead of guessing");
    expect(panel).toHaveTextContent("Declined · not enough evidence");
    expect(panel).toHaveTextContent("Not enough info");
  });

  it("stops while the pointer or focus is on it, and carries on after", () => {
    stubMotion(false);
    renderCard();
    act(() => vi.advanceTimersByTime(0));
    const card = screen.getByTestId("answer-card");

    fireEvent.mouseEnter(card);
    act(() => vi.advanceTimersByTime(30000));
    expect(selected()).toHaveTextContent("Guideline");

    fireEvent.mouseLeave(card);
    act(() => vi.advanceTimersByTime(8000));
    expect(selected()).toHaveTextContent("Medication");

    fireEvent.focus(card);
    act(() => vi.advanceTimersByTime(30000));
    expect(selected()).toHaveTextContent("Medication");
  });

  it("has a pause button that stops it and a play button that restarts it", () => {
    stubMotion(false);
    renderCard();
    act(() => vi.advanceTimersByTime(0));

    fireEvent.click(screen.getByRole("button", { name: "Pause examples" }));
    act(() => vi.advanceTimersByTime(30000));
    expect(selected()).toHaveTextContent("Guideline");

    fireEvent.click(screen.getByRole("button", { name: "Play examples" }));
    act(() => vi.advanceTimersByTime(8000));
    expect(selected()).toHaveTextContent("Medication");
  });

  it("under reduced motion it never moves by itself, offers no pause (nothing to pause) and shows the answer finished", () => {
    stubMotion(true);
    renderCard();
    act(() => vi.advanceTimersByTime(0));

    act(() => vi.advanceTimersByTime(60000));

    expect(selected()).toHaveTextContent("Guideline");
    expect(screen.queryByRole("button", { name: /Pause examples/ })).not.toBeInTheDocument();
    expect(document.querySelector(".animate-toast-in")).toBeNull();
  });

  it("the reader can pick an example, with the arrow keys too, and one tab stays in the tab order", () => {
    stubMotion(true);
    renderCard();
    const tabs = screen.getAllByRole("tab");

    fireEvent.click(tabs[1]);
    expect(selected()).toHaveTextContent("Medication");
    fireEvent.keyDown(tabs[1], { key: "ArrowRight" });
    expect(selected()).toHaveTextContent("Declines");
    expect(tabs[2]).toHaveFocus();
    fireEvent.keyDown(tabs[2], { key: "ArrowRight" });
    expect(selected()).toHaveTextContent("Guideline");
    expect(tabs.map((t) => t.getAttribute("tabindex"))).toEqual(["0", "-1", "-1"]);
  });

  it("keeps its height: every example is also in the page, invisibly, in the same cell", () => {
    stubMotion(true);
    renderCard();

    const sizers = document.querySelectorAll("[aria-hidden='true'].invisible.col-start-1.row-start-1");
    expect(sizers).toHaveLength(ANSWER_EXAMPLES.length);
    // They hold the same text, so the card is as tall as the tallest example.
    expect(sizers[2]).toHaveTextContent("Declined · not enough evidence");
  });

  it("builds an answer up in order when motion is allowed: question first, outcome last", () => {
    stubMotion(false);
    renderCard();
    act(() => vi.advanceTimersByTime(0));

    const delays = Array.from(screen.getByRole("tabpanel").querySelectorAll("[data-delay]")).map((el) =>
      Number(el.getAttribute("data-delay")),
    );

    expect(delays).toHaveLength(4);
    expect(delays).toEqual([...delays].sort((a, b) => a - b));
    expect(delays[0]).toBe(0);
    expect(Math.max(...delays)).toBeGreaterThanOrEqual(1500);
  });
});

describe("the examples", () => {
  const en = EN as Record<string, string>;
  const es = ES as Record<string, string>;

  it("every text is in both languages", () => {
    for (const example of ANSWER_EXAMPLES) {
      const keys = [
        example.tabKey,
        example.questionKey,
        example.answerKey,
        example.outcomeKey,
        ...example.claims.map((c) => c.textKey),
      ];
      for (const key of keys) {
        expect(en[key], `en ${key}`).toBeTruthy();
        expect(es[key], `es ${key}`).toBeTruthy();
      }
    }
  });

  it("a cited example names a source, and the declined one names none and says it does not guess", () => {
    const [guideline, drug, decline] = ANSWER_EXAMPLES;

    expect(guideline.citations.length).toBeGreaterThan(0);
    expect(drug.citations.length).toBeGreaterThan(0);
    expect(decline.citations).toEqual([]);
    expect(decline.outcome).toBe("decline");
    expect(en[decline.answerKey]).toMatch(/declines to answer instead of guessing/);
  });

  it("only uses agents that exist", () => {
    for (const example of ANSWER_EXAMPLES) {
      expect([
        "marketing.agentName.evidence",
        "marketing.agentName.drugSafety",
        "marketing.agentName.radiology",
      ]).toContain(example.agentKey);
    }
  });
});
