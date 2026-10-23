import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Reveal from "@/components/landing/reveal";

let callback: IntersectionObserverCallback = () => {};
class FakeObserver {
  constructor(cb: IntersectionObserverCallback) {
    callback = cb;
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}

function mount({ top = 2000, reduced = false }: { top?: number; reduced?: boolean } = {}) {
  vi.stubGlobal("IntersectionObserver", FakeObserver);
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: reduced && q.includes("reduce"),
    media: q,
    addEventListener() {},
    removeEventListener() {},
  }));
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top } as DOMRect);
  render(<Reveal>content</Reveal>);
  return screen.getByText("content");
}

describe("Reveal", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("holds back a block that starts below the fold, and shows it once it is scrolled to", () => {
    const el = mount();
    expect(el).toHaveAttribute("data-reveal", "hidden");

    act(() => callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));

    expect(el).toHaveAttribute("data-reveal", "shown");
  });

  it("never hides a block that is already on screen at load", () => {
    expect(mount({ top: 100 })).toHaveAttribute("data-reveal", "shown");
  });

  it("never hides anything under reduced motion", () => {
    expect(mount({ reduced: true })).toHaveAttribute("data-reveal", "shown");
  });

  it("never hides anything where there is no IntersectionObserver", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top: 3000 } as DOMRect);
    render(<Reveal>content</Reveal>);

    expect(screen.getByText("content")).toHaveAttribute("data-reveal", "shown");
  });
});
