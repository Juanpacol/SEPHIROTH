import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Masonry, { type MasonryItem } from "@/components/landing/masonry";

const to = vi.fn();
vi.mock("gsap", () => ({
  gsap: { to: (...args: unknown[]) => to(...args), set: vi.fn(), fromTo: vi.fn() },
}));

const ITEMS: MasonryItem[] = [
  { id: "xray", img: "/x.webp", height: 400, title: "Chest X-ray", caption: "Plain film" },
  { id: "ct", img: "/c.webp", height: 500, title: "Brain CT", caption: "Axial slice", url: "https://example.org/ct" },
  { id: "bare", img: "/b.webp", height: 300 },
];

/** A device with (or without) a pointer that can hover, and a width to lay out in. */
function stubEnvironment({ hover }: { hover: boolean }) {
  vi.stubGlobal(
    "matchMedia",
    (query: string) => ({
      matches: query.includes("hover: hover") ? hover : false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(private cb: (entries: unknown[]) => void) {}
      observe() {
        this.cb([{ contentRect: { width: 1200, height: 800 } }]);
      }
      disconnect() {}
    },
  );
}

const cards = () => screen.getAllByRole("group");

describe("Masonry", () => {
  beforeEach(() => {
    to.mockClear();
    stubEnvironment({ hover: true });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("makes every card reachable by keyboard, as a named group", () => {
    render(<Masonry items={ITEMS} />);

    expect(cards()).toHaveLength(3);
    for (const card of cards()) expect(card).toHaveAttribute("tabindex", "0");
    expect(cards()[0]).toHaveAccessibleName("Chest X-ray");
    expect(cards()[2]).toHaveAccessibleName("Medical imaging analysis example");
  });

  it("keeps each caption in the page for every device, so none depends on hover to exist", () => {
    render(<Masonry items={ITEMS} />);

    expect(screen.getByText("Plain film")).toBeInTheDocument();
    expect(screen.getByText("Axial slice")).toBeInTheDocument();
  });

  it("only a card with a url looks like a link", () => {
    render(<Masonry items={ITEMS} />);

    const [plain, linked] = cards();
    expect(plain.className).not.toMatch(/link/);
    expect(linked.className).toMatch(/link/);
  });

  it("does not open anything when a card without a url is clicked, and opens the one with a url", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<Masonry items={ITEMS} />);

    fireEvent.click(cards()[0]);
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(cards()[1]);
    expect(open).toHaveBeenCalledWith("https://example.org/ct", "_blank", "noopener");
    open.mockRestore();
  });

  it("lifts a card a little on hover when the device has a pointer, and never shrinks it", () => {
    render(<Masonry items={ITEMS} />);

    fireEvent.mouseEnter(cards()[0]);

    const scales = to.mock.calls.map(([, vars]) => (vars as { scale?: number }).scale).filter((s) => s !== undefined);
    expect(scales).toEqual([1.02]);
    expect(Math.min(...(scales as number[]))).toBeGreaterThanOrEqual(1);
  });

  it("puts the card back when the pointer leaves", () => {
    render(<Masonry items={ITEMS} />);

    fireEvent.mouseEnter(cards()[0]);
    fireEvent.mouseLeave(cards()[0]);

    const scales = to.mock.calls.map(([, vars]) => (vars as { scale?: number }).scale).filter((s) => s !== undefined);
    expect(scales).toEqual([1.02, 1]);
  });

  it("does nothing on hover when the device cannot hover, so a tap leaves no stuck card", () => {
    stubEnvironment({ hover: false });
    render(<Masonry items={ITEMS} />);

    fireEvent.mouseEnter(cards()[0]);
    fireEvent.mouseLeave(cards()[0]);

    expect(to).not.toHaveBeenCalled();
  });

  it("honours a hover scale the caller chooses", () => {
    render(<Masonry items={ITEMS} hoverScale={1.05} />);

    fireEvent.mouseEnter(cards()[0]);

    expect(to.mock.calls[0][1]).toMatchObject({ scale: 1.05 });
  });
});
