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

describe("the See cell's study", () => {
  const media = LANDING_FEATURES.find((f) => f.id === "see")!.media;

  it("is one pathology study with a description and a label, in both languages", () => {
    expect(media.kind).toBe("slides");
    if (media.kind !== "slides") return;
    expect(media.slides).toHaveLength(1);
    const [slide] = media.slides;
    expect(slide.src).toBe("/landing/analysis/pathology.webp");
    expect(existsSync(path.join(__dirname, "../../..", "public", slide.src))).toBe(true);
    for (const key of [slide.titleKey, slide.captionKey]) {
      expect((EN as Record<string, string>)[key], key).toBeTruthy();
      expect((ES as Record<string, string>)[key], key).toBeTruthy();
    }
  });

  it("stays where it is: no drift with the scroll, and nothing takes its turn", () => {
    vi.useFakeTimers();
    try {
      const { container } = render(wrap(<FeatureMediaView media={media} playing />));
      const src = () => container.querySelector("[data-slide='current']")!.getAttribute("src");
      const before = src();

      act(() => vi.advanceTimersByTime(60000));

      expect(src()).toBe(before);
      expect(container.querySelector("[data-parallax]")).toBeNull();
      expect(container.querySelector("[data-slide-label]")).toHaveTextContent(
        "Pathology · H&E-stained tissue",
      );
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("the cells with a single picture", () => {
  const cells = LANDING_FEATURES.filter((f) => f.media.kind === "image");

  it("are Ask, Cite, Verify, Follow up and Share, each with a file and a description in both languages", () => {
    expect(cells.map((c) => c.id)).toEqual(["ask", "cite", "verify", "follow", "share"]);
    for (const cell of cells) {
      if (cell.media.kind !== "image") continue;
      expect(existsSync(path.join(__dirname, "../../..", "public", cell.media.src)), cell.media.src).toBe(
        true,
      );
      expect((EN as Record<string, string>)[cell.media.altKey], cell.media.altKey).toBeTruthy();
      expect((ES as Record<string, string>)[cell.media.altKey], cell.media.altKey).toBeTruthy();
    }
  });

  it("stay where they are: no drift with the scroll, and nothing takes its turn", () => {
    for (const cell of cells) {
      const { container } = render(wrap(<FeatureMediaView media={cell.media} playing />));
      expect(container.querySelector("[data-parallax]"), cell.id).toBeNull();
      expect(container.querySelector("[data-slides], [data-sequence]"), cell.id).toBeNull();
    }
  });
});
