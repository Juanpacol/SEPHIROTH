import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FeatureShowcase from "@/components/landing/feature-showcase";
import FeatureMediaView from "@/components/landing/feature-media";
import { LANDING_FEATURES, type FeatureMedia } from "@/lib/landing-features";
import { LanguageProvider } from "@/lib/language";

let fire: (id: string, intersecting: boolean) => void = () => {};
class FakeObserver {
  constructor(cb: IntersectionObserverCallback) {
    fire = (id, isIntersecting) =>
      cb(
        [{ target: document.getElementById(id)!, isIntersecting } as unknown as IntersectionObserverEntry],
        this as never,
      );
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}

const wrap = (ui: React.ReactNode) => <LanguageProvider>{ui}</LanguageProvider>;

describe("FeatureShowcase", () => {
  beforeEach(() => vi.stubGlobal("IntersectionObserver", FakeObserver));
  afterEach(() => vi.unstubAllGlobals());

  it("lists every feature, numbered, with its title and what it does", () => {
    render(wrap(<FeatureShowcase />));

    const articles = screen.getAllByRole("article");
    expect(articles).toHaveLength(LANDING_FEATURES.length);
    expect(within(articles[0]).getByText(/01 · Ask/)).toBeInTheDocument();
    expect(within(articles[3]).getByRole("heading", { name: "Images, described" })).toBeInTheDocument();
    expect(articles[3]).toHaveTextContent("It never diagnoses");
  });

  it("starts on the first feature and follows the one in the middle of the screen", () => {
    render(wrap(<FeatureShowcase />));
    const layers = () => Array.from(document.querySelectorAll("[data-layer]"));
    expect(layers().map((l) => l.getAttribute("aria-hidden"))).toEqual([
      "false",
      "true",
      "true",
      "true",
      "true",
      "true",
    ]);

    act(() => fire("feature-verify", true));

    expect(layers().map((l) => l.getAttribute("aria-hidden"))).toEqual([
      "true",
      "true",
      "false",
      "true",
      "true",
      "true",
    ]);
    expect(document.getElementById("feature-verify")).toHaveAttribute("data-active", "true");
    expect(document.getElementById("feature-ask")).not.toHaveAttribute("data-active");
  });

  it("only the feature in view is revealed in the panel, the rest are clipped and hidden from assistive technology", () => {
    render(wrap(<FeatureShowcase />));
    const [first, second] = Array.from(document.querySelectorAll("[data-layer]"));

    expect(first.className).toContain("opacity-100");
    expect(second.className).toContain("opacity-0");
    expect(second.className).toContain("clip-path:inset(0_0_100%_0)");
    expect(second).toHaveAttribute("aria-hidden", "true");
  });

  it("every feature has a small-screen copy of its media, so the sticky panel is not the only place it shows", () => {
    render(wrap(<FeatureShowcase />));

    for (const article of screen.getAllByRole("article")) {
      expect(article.querySelector(".lg\\:hidden")).not.toBeNull();
    }
  });
});

describe("FeatureMediaView", () => {
  // jsdom does not implement media playback.
  beforeEach(() => {
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });
  const video: FeatureMedia = {
    kind: "video",
    src: "/a.mp4",
    webm: "/a.webm",
    poster: "/a.webp",
    altKey: "marketing.features.see.alt",
  };

  it("a feature with no media shows its number and verb as a tile hidden from assistive technology", () => {
    const { container } = render(
      wrap(<FeatureMediaView media={{ kind: "placeholder" }} index={2} verb="Verify" />),
    );

    expect(container.querySelector("[aria-hidden='true']")).toHaveTextContent("Verify");
    expect(container).toHaveTextContent("03");
  });

  it("an image carries its description", () => {
    render(
      wrap(
        <FeatureMediaView
          media={{ kind: "image", src: "/x.webp", altKey: "marketing.features.see.alt" }}
          index={3}
          verb="See"
        />,
      ),
    );

    expect(screen.getByRole("img", { name: "A chest X-ray, one of the example studies" })).toHaveAttribute(
      "src",
      "/x.webp",
    );
  });

  it("a video is silent, loops, plays inline and offers both formats", () => {
    const { container } = render(wrap(<FeatureMediaView media={video} index={0} verb="Ask" />));
    const el = container.querySelector("video")!;

    expect(el.muted).toBe(true);
    expect(el.loop).toBe(true);
    expect(el.getAttribute("playsinline")).not.toBeNull();
    expect(el.getAttribute("poster")).toBe("/a.webp");
    expect(Array.from(el.querySelectorAll("source")).map((s) => s.getAttribute("type"))).toEqual([
      "video/webm",
      "video/mp4",
    ]);
  });

  it("a video plays only while its feature is in view, and never under reduced motion", () => {
    const play = vi.fn(() => Promise.resolve());
    const pause = vi.fn();
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(play);
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(pause);
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: false,
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }));

    const { rerender } = render(wrap(<FeatureMediaView media={video} index={0} verb="Ask" playing />));
    expect(play).toHaveBeenCalledTimes(1);

    rerender(wrap(<FeatureMediaView media={video} index={0} verb="Ask" playing={false} />));
    expect(pause).toHaveBeenCalled();

    play.mockClear();
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: true,
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }));
    rerender(wrap(<FeatureMediaView media={video} index={0} verb="Ask" playing={false} />));
    rerender(wrap(<FeatureMediaView media={video} index={0} verb="Ask" playing />));
    expect(play).not.toHaveBeenCalled();
  });

  it("the small-screen copy of a video is its poster, a plain picture", () => {
    const { container } = render(wrap(<FeatureMediaView media={video} index={0} verb="Ask" still />));

    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByRole("img")).toHaveAttribute("src", "/a.webp");
  });
});
