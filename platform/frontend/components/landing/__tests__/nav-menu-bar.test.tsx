import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NavMenuBar from "@/components/landing/nav-menu-bar";
import { LanguageProvider } from "@/lib/language";

/** jsdom has no layout, so the scroll-spy's IntersectionObserver is replaced by one the
 * test can drive. */
let fire: (id: string, intersecting: boolean) => void = () => {};
class FakeObserver {
  static targets: Element[] = [];
  private callback: IntersectionObserverCallback;
  constructor(cb: IntersectionObserverCallback) {
    this.callback = cb;
    fire = (id, isIntersecting) => {
      const target = document.getElementById(id)!;
      this.callback([{ target, isIntersecting } as unknown as IntersectionObserverEntry], this as never);
    };
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}

function stubHover(hover: boolean | "unsupported") {
  vi.stubGlobal(
    "matchMedia",
    hover === "unsupported"
      ? undefined
      : (q: string) => ({
          matches: q.includes("hover: hover") ? hover : false,
          addEventListener() {},
          removeEventListener() {},
        }),
  );
}

const renderBar = () =>
  render(
    <LanguageProvider>
      <div id="faq" />
      <NavMenuBar />
    </LanguageProvider>,
  );
const button = (name: string | RegExp) => screen.getByRole("button", { name });

describe("NavMenuBar", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("IntersectionObserver", FakeObserver);
    stubHover(false);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("starts closed, with every button saying what it controls", () => {
    renderBar();

    for (const name of [/Product/, /For patients/, /Open source/]) {
      expect(screen.getByRole("button", { name })).toHaveAttribute("aria-expanded", "false");
      expect(screen.getByRole("button", { name })).toHaveAttribute("aria-controls");
    }
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("opens on click as a region named after the button, and closes on a second click", () => {
    renderBar();

    fireEvent.click(button(/Product/));
    expect(button(/Product/)).toHaveAttribute("aria-expanded", "true");
    const region = screen.getByRole("region", { name: "Product" });
    expect(button(/Product/).getAttribute("aria-controls")).toBe(region.id);
    expect(region).toHaveTextContent("How it works");

    fireEvent.click(button(/Product/));
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("only one panel is open at a time", () => {
    renderBar();

    fireEvent.click(button(/Product/));
    fireEvent.click(button(/Open source/));

    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(screen.getByRole("region", { name: "Open source" })).toBeInTheDocument();
    expect(button(/Product/)).toHaveAttribute("aria-expanded", "false");
  });

  it("Escape closes it and gives the focus back to its button", () => {
    renderBar();
    button(/For patients/).focus();
    fireEvent.click(button(/For patients/));

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    expect(button(/For patients/)).toHaveFocus();
  });

  it("a click outside closes it", () => {
    renderBar();
    fireEvent.click(button(/Product/));

    fireEvent.mouseDown(document.body);

    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("choosing an item closes it", () => {
    renderBar();
    fireEvent.click(button(/For patients/));

    fireEvent.click(screen.getByRole("link", { name: /Set up your portal account/ }));

    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("outside links open in a new tab, safely, and say so; internal ones do not", () => {
    renderBar();
    fireEvent.click(button(/Open source/));

    const repo = screen.getByRole("link", { name: /Repository/ });
    expect(repo).toHaveAttribute("target", "_blank");
    expect(repo).toHaveAttribute("rel", "noopener noreferrer");
    expect(repo).toHaveTextContent("(opens in a new tab)");

    fireEvent.click(button(/For patients/));
    expect(screen.getByRole("link", { name: /Sign in/ })).not.toHaveAttribute("target");
  });

  it("marks the section the reader is in, inside the panel", () => {
    renderBar();
    act(() => fire("faq", true));

    fireEvent.click(button(/Product/));

    expect(screen.getByRole("link", { name: /FAQ/ })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("link", { name: /How it works/ })).not.toHaveAttribute("aria-current");
    expect(button(/Product/)).toHaveAttribute("data-here", "true");
  });

  it("opens on hover only where the device can hover, after a short pause", () => {
    stubHover(true);
    renderBar();
    const productWrapper = button(/Product/).parentElement!;

    fireEvent.mouseEnter(productWrapper);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    act(() => vi.advanceTimersByTime(100));
    expect(screen.getByRole("region", { name: "Product" })).toBeInTheDocument();

    fireEvent.mouseLeave(productWrapper.parentElement!);
    act(() => vi.advanceTimersByTime(200));
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("never opens on hover on a touch device, nor where matchMedia is missing", () => {
    for (const mode of [false, "unsupported"] as const) {
      stubHover(mode);
      const { unmount } = renderBar();
      fireEvent.mouseEnter(button(/Product/).parentElement!);
      act(() => vi.advanceTimersByTime(500));
      expect(screen.queryByRole("region")).not.toBeInTheDocument();
      unmount();
    }
  });
});
