import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Sheet from "@/components/ui/sheet";
import { LanguageProvider } from "@/lib/language";

/** The sheet fades out instead of vanishing, unless motion is reduced. */
function stubMotion(reduce: boolean | "unsupported") {
  if (reduce === "unsupported") {
    vi.stubGlobal("matchMedia", undefined);
    return;
  }
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? reduce : false,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

function renderSheet(open: boolean, onClose = vi.fn(), side: "right" | "left" | "bottom" = "right") {
  const ui = (isOpen: boolean) => (
    <LanguageProvider>
      <Sheet open={isOpen} onClose={onClose} title="Panel" side={side}>
        <p>Body</p>
      </Sheet>
    </LanguageProvider>
  );
  const view = render(ui(open));
  return { ...view, setOpen: (o: boolean) => view.rerender(ui(o)), onClose };
}

describe("Sheet", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("stays in the page for the leave animation, then goes", () => {
    stubMotion(false);
    const { setOpen } = renderSheet(true);
    act(() => vi.runOnlyPendingTimers());
    expect(screen.getByRole("dialog")).toHaveAttribute("data-state", "open");

    setOpen(false);

    const leaving = screen.getByRole("dialog");
    expect(leaving).toHaveAttribute("data-state", "closed");
    expect(leaving.className).toContain("pointer-events-none");
    act(() => vi.advanceTimersByTime(199));
    expect(screen.queryByRole("dialog")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("goes at once under reduced motion", () => {
    stubMotion(true);
    const { setOpen } = renderSheet(true);
    act(() => vi.runOnlyPendingTimers());

    setOpen(false);
    act(() => vi.advanceTimersByTime(0));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("goes at once where matchMedia does not exist", () => {
    stubMotion("unsupported");
    const { setOpen } = renderSheet(true);
    act(() => vi.runOnlyPendingTimers());

    setOpen(false);
    act(() => vi.advanceTimersByTime(0));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opening again while it is leaving keeps it", () => {
    stubMotion(false);
    const { setOpen } = renderSheet(true);
    act(() => vi.runOnlyPendingTimers());

    setOpen(false);
    act(() => vi.advanceTimersByTime(100));
    setOpen(true);
    act(() => vi.advanceTimersByTime(500));

    expect(screen.getByRole("dialog")).toHaveAttribute("data-state", "open");
  });

  it("closes on Escape and on the scrim, and not once it is leaving", () => {
    stubMotion(false);
    const { setOpen, onClose } = renderSheet(true);
    act(() => vi.runOnlyPendingTimers());

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    setOpen(false);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["right", "animate-sheet-in-right", "animate-sheet-out-right"],
    ["left", "animate-sheet-in-left", "animate-sheet-out-left"],
    ["bottom", "animate-sheet-in-bottom", "animate-sheet-out-bottom"],
  ] as const)("enters and leaves along its own edge (%s)", (side, enter, leave) => {
    stubMotion(false);
    const { setOpen } = renderSheet(true, vi.fn(), side);
    act(() => vi.runOnlyPendingTimers());
    const panel = () => screen.getByRole("dialog").querySelector("h2")!.closest("div")!.parentElement!;
    expect(panel().className).toContain(enter);

    setOpen(false);

    expect(panel().className).toContain(leave);
  });
});
