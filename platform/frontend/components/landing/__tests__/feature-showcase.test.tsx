import { existsSync } from "node:fs";
import path from "node:path";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import EN from "@/lib/i18n/dictionaries.en";
import ES from "@/lib/i18n/dictionaries.es";
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
        [
          {
            target: document.querySelector(`[data-feature="${id}"]`)!,
            isIntersecting,
          } as unknown as IntersectionObserverEntry,
        ],
        this as never,
      );
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}

const wrap = (ui: React.ReactNode) => <LanguageProvider>{ui}</LanguageProvider>;

describe("FeatureShowcase", () => {
  beforeEach(() => {
    vi.stubGlobal("IntersectionObserver", FakeObserver);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("is a grid of six cells: a numbered label, a title and a paragraph each", () => {
    render(wrap(<FeatureShowcase />));

    const articles = screen.getAllByRole("article");
    expect(articles).toHaveLength(LANDING_FEATURES.length);
    expect(within(articles[0]).getByText("#1 Ask")).toBeInTheDocument();
    expect(within(articles[4]).getByText("#5 Follow up")).toBeInTheDocument();
    expect(within(articles[3]).getByRole("heading", { name: "Images, described" })).toBeInTheDocument();
    expect(articles[3]).toHaveTextContent("It never diagnoses");
  });

  it("three columns from lg, two from md, one below", () => {
    render(wrap(<FeatureShowcase />));

    const grid = screen.getByRole("list");
    expect(grid.className).toContain("grid-cols-1");
    expect(grid.className).toContain("md:grid-cols-2");
    expect(grid.className).toContain("lg:grid-cols-3");
  });

  it("every cell ends in a square frame for its picture, which the picture can drift in", () => {
    render(wrap(<FeatureShowcase />));

    for (const article of screen.getAllByRole("article")) {
      const frame = article.querySelector("[data-parallax-frame]")!;
      expect(frame.className).toContain("aspect-square");
      expect(frame.className).toContain("overflow-hidden");
    }
  });

  it("the cells are in the order the reader meets them", () => {
    render(wrap(<FeatureShowcase />));

    const ids = screen.getAllByRole("article").map((a) => a.getAttribute("data-feature"));
    expect(ids).toEqual(LANDING_FEATURES.map((f) => f.id));
  });

  it("a cell's video plays only while that cell is on screen", () => {
    const withVideo: FeatureMedia = {
      kind: "video",
      src: "/a.mp4",
      poster: "/a.webp",
      altKey: "marketing.features.see.alt",
    };
    const feature = LANDING_FEATURES[0];
    const original = feature.media;
    feature.media = withVideo;
    try {
      const play = vi.spyOn(HTMLMediaElement.prototype, "play");
      vi.stubGlobal("matchMedia", (q: string) => ({
        matches: false,
        media: q,
        addEventListener() {},
        removeEventListener() {},
      }));
      render(wrap(<FeatureShowcase />));
      expect(play).not.toHaveBeenCalled();

      act(() => fire(feature.id, true));

      expect(play).toHaveBeenCalledTimes(1);
    } finally {
      feature.media = original;
    }
  });
});

describe("the See cell's slides", () => {
  const slides = LANDING_FEATURES.find((f) => f.id === "see")!.media;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: false,
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });
  const current = (container: HTMLElement) => container.querySelector("[data-slide='current']")!;

  it("carries the ten example studies, each with a description and a label", () => {
    expect(slides.kind).toBe("slides");
    if (slides.kind !== "slides") return;
    expect(slides.slides).toHaveLength(10);
    for (const slide of slides.slides) {
      expect(slide.src).toMatch(/^\/landing\/analysis\/.+\.webp$/);
      expect((EN as Record<string, string>)[slide.captionKey], slide.captionKey).toBeTruthy();
      expect((ES as Record<string, string>)[slide.titleKey], slide.titleKey).toBeTruthy();
    }
  });

  it("every file exists, so no slide is a broken picture", () => {
    if (slides.kind !== "slides") return;
    for (const slide of slides.slides) {
      expect(existsSync(path.join(__dirname, "../../..", "public", slide.src)), slide.src).toBe(true);
    }
  });

  it("shows the first and does not move while its cell is off screen", () => {
    const { container } = render(wrap(<FeatureMediaView media={slides} playing={false} />));

    act(() => vi.advanceTimersByTime(60000));

    expect(current(container)).toHaveAttribute("src", "/landing/analysis/xray.webp");
  });

  it("takes turns while on screen, cross-fading, and wraps round to the first", () => {
    const { container } = render(wrap(<FeatureMediaView media={slides} playing />));

    act(() => vi.advanceTimersByTime(3400));
    expect(current(container)).toHaveAttribute("src", "/landing/analysis/ct-brain.webp");
    act(() => vi.advanceTimersByTime(3400));
    expect(current(container)).toHaveAttribute("src", "/landing/analysis/mri-brain.webp");
    // Each turn schedules the next once React has rendered it, so step one turn at a time.
    for (let i = 0; i < 8; i++) act(() => vi.advanceTimersByTime(3400));
    expect(current(container)).toHaveAttribute("src", "/landing/analysis/xray.webp");
    expect(container.querySelector("img[data-slide='current']")!.className).toContain("duration-slow");
  });

  it("only the one on show is announced, and the label names it", () => {
    const { container } = render(wrap(<FeatureMediaView media={slides} playing />));
    act(() => vi.advanceTimersByTime(3400));

    const images = Array.from(container.querySelectorAll("img"));
    expect(images.filter((i) => i.getAttribute("aria-hidden") === "false")).toHaveLength(1);
    expect(container.querySelector("[data-slide-label]")).toHaveTextContent("CT · Sagittal brain scan");
  });

  it("holds still under the pointer, and under reduced motion shows the first for good", () => {
    const { container, unmount } = render(wrap(<FeatureMediaView media={slides} playing />));
    fireEvent.mouseEnter(container.querySelector("[data-slides]")!);
    act(() => vi.advanceTimersByTime(30000));
    expect(current(container)).toHaveAttribute("src", "/landing/analysis/xray.webp");
    unmount();

    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: true,
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }));
    const reduced = render(wrap(<FeatureMediaView media={slides} playing />));
    act(() => vi.advanceTimersByTime(30000));
    expect(current(reduced.container)).toHaveAttribute("src", "/landing/analysis/xray.webp");
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

  it("a feature with no picture gets a generated tile in its own pattern, hidden from assistive technology", () => {
    for (const pattern of ["rays", "lines", "checks", "dots", "frames", "waves"] as const) {
      const { container, unmount } = render(wrap(<FeatureMediaView media={{ kind: "tile", pattern }} />));
      const tile = container.querySelector(`[data-tile="${pattern}"]`)!;
      expect(tile).toHaveAttribute("aria-hidden", "true");
      unmount();
    }
  });

  it("an image carries its description, drifts inside its frame and is tinted to the blue by default", () => {
    const { container } = render(
      wrap(
        <FeatureMediaView media={{ kind: "image", src: "/x.webp", altKey: "marketing.features.see.alt" }} />,
      ),
    );

    const img = screen.getByRole("img", { name: "A chest X-ray, one of the example studies" });
    expect(img).toHaveAttribute("src", "/x.webp");
    expect(img).toHaveAttribute("data-parallax");
    expect(img.className).toContain("scale-[1.2]");
    expect(container.querySelector(".mix-blend-multiply")).not.toBeNull();
  });

  it("an image can be left as it is", () => {
    const { container } = render(
      wrap(
        <FeatureMediaView
          media={{ kind: "image", src: "/x.webp", altKey: "marketing.features.see.alt", tone: "natural" }}
        />,
      ),
    );

    expect(container.querySelector(".mix-blend-multiply")).toBeNull();
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("a video is silent, loops, plays inline and offers both formats", () => {
    const { container } = render(wrap(<FeatureMediaView media={video} />));
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

  it("a video plays only while it is on screen, and never under reduced motion", () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause");
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: false,
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }));

    const { rerender } = render(wrap(<FeatureMediaView media={video} playing />));
    expect(play).toHaveBeenCalledTimes(1);

    rerender(wrap(<FeatureMediaView media={video} playing={false} />));
    expect(pause).toHaveBeenCalled();

    play.mockClear();
    vi.stubGlobal("matchMedia", (q: string) => ({
      matches: true,
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }));
    rerender(wrap(<FeatureMediaView media={video} playing={false} />));
    rerender(wrap(<FeatureMediaView media={video} playing />));
    expect(play).not.toHaveBeenCalled();
  });
});
