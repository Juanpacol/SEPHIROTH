import { describe, expect, it } from "vitest";
import { clamp01, damp, footerLift, footerProgress, heroProgress, heroShift } from "@/lib/scroll-effects";

/** The maths of the landing's scroll-linked motion. */
describe("footerProgress", () => {
  const base = { viewportHeight: 900, footerTop: 5000, footerHeight: 800 };

  it("is 0 until the footer's top edge reaches the bottom of the screen", () => {
    expect(footerProgress({ ...base, scrollY: 0 })).toBe(0);
    expect(footerProgress({ ...base, scrollY: 4100 })).toBe(0);
  });

  it("grows as the footer comes into view and is 1 once most of it is showing", () => {
    const at = (scrollY: number) => footerProgress({ ...base, scrollY });
    expect(at(4300)).toBeGreaterThan(0);
    expect(at(4500)).toBeGreaterThan(at(4300));
    expect(at(4100 + 800 * 0.9)).toBeCloseTo(1, 5);
    expect(at(9000)).toBe(1);
  });

  it("never leaves 0..1, and survives a footer of no height", () => {
    for (const scrollY of [-100, 0, 4500, 99999]) {
      const p = footerProgress({ ...base, scrollY });
      expect(p).toBeGreaterThanOrEqual(0);
      expect(p).toBeLessThanOrEqual(1);
    }
    expect(Number.isFinite(footerProgress({ ...base, footerHeight: 0, scrollY: 4600 }))).toBe(true);
  });

  it("a footer taller than the screen finishes after one screen of scrolling, not after its height", () => {
    const tall = { viewportHeight: 900, footerTop: 5000, footerHeight: 3000 };
    expect(footerProgress({ ...tall, scrollY: 4100 + 900 * 0.9 })).toBeCloseTo(1, 5);
  });
});

describe("hero", () => {
  it("holds still at first: the eased progress is small while the reader has barely moved", () => {
    expect(heroProgress(0, 800)).toBe(0);
    expect(heroProgress(80, 800)).toBeLessThan(0.02);
    expect(heroProgress(400, 800)).toBeCloseTo(0.25, 5);
    expect(heroProgress(800, 800)).toBe(1);
    expect(heroProgress(5000, 800)).toBe(1);
  });

  it("drifts at about a third of the scroll speed, up to one screen", () => {
    expect(heroShift(0, 900)).toBe(0);
    expect(heroShift(1000, 900)).toBeCloseTo(350, 5);
    expect(heroShift(10000, 900)).toBe(900);
    expect(heroShift(-50, 900)).toBe(0);
  });
});

describe("footerLift", () => {
  it("is 0 once the footer has arrived and largest when it has not started", () => {
    expect(footerLift(1, 100)).toBe(0);
    expect(footerLift(0, 100)).toBeGreaterThan(footerLift(0.5, 100));
  });

  it("eases out: most of the rise happens early, the end is gentle", () => {
    const early = footerLift(0, 100) - footerLift(0.25, 100);
    const late = footerLift(0.75, 100) - footerLift(1, 100);
    expect(early).toBeGreaterThan(late * 5);
  });

  it("scales with the distance and ignores a progress outside 0..1", () => {
    expect(footerLift(0, 100)).toBe(100);
    expect(footerLift(0, 200)).toBeCloseTo(footerLift(0, 100) * 2, 5);
    expect(footerLift(-5, 100)).toBe(footerLift(0, 100));
    expect(footerLift(5, 100)).toBe(0);
  });
});

describe("damp", () => {
  it("moves toward the target without overshooting it", () => {
    let value = 0;
    for (let i = 0; i < 200; i++) {
      value = damp(value, 100, 1 / 60);
      expect(value).toBeLessThanOrEqual(100);
    }
    expect(value).toBeGreaterThan(99);
  });

  it("covers the same share of the distance per second whatever the frame rate", () => {
    const run = (fps: number) => {
      let v = 0;
      for (let i = 0; i < fps; i++) v = damp(v, 1, 1 / fps);
      return v;
    };
    expect(run(30)).toBeCloseTo(run(144), 6);
  });

  it("stands still when it is already there, and does not move when no time has passed", () => {
    expect(damp(5, 5, 1 / 60)).toBe(5);
    expect(damp(0, 10, 0)).toBe(0);
  });

  it("clamp01 pins to 0..1", () => {
    expect([clamp01(-1), clamp01(0.4), clamp01(7)]).toEqual([0, 0.4, 1]);
  });
});
