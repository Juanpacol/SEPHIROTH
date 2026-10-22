"use client";

/** Writes the landing page's scroll-linked motion to CSS variables on <html>:
 *
 *   --hero-shift      px the hero's content has drifted down
 *   --hero-progress   0..1, how far the hero has scrolled away
 *   --footer-progress 0..1, how far the footer has come into view
 *   --footer-lift     px the footer still has to rise
 *   --py-img          on each `[data-parallax]` picture: px it has drifted inside its frame
 *
 * One loop, started by a scroll or resize and stopped when every value has settled, so
 * a page nobody is scrolling costs nothing. The values follow the scroll with a little
 * lag (`damp`) instead of jumping to it. With reduced motion the variables are set once
 * to their resting values and nothing moves.
 *
 * The page's own CSS reads the variables with a resting default (`var(--x, 1)`), so a
 * page that has not run this yet, or never will, looks finished. */

import { useEffect } from "react";
import {
  clamp01,
  damp,
  footerLift,
  footerProgress,
  heroProgress,
  heroShift,
  parallaxShift,
} from "@/lib/scroll-effects";

const SETTLED = 0.002;
const RATE = 9;

export default function ScrollEffects() {
  useEffect(() => {
    const root = document.documentElement;
    const set = (name: string, value: string) => root.style.setProperty(name, value);
    const unset = () => {
      for (const name of ["--hero-shift", "--hero-progress", "--footer-progress", "--footer-lift"]) {
        root.style.removeProperty(name);
      }
    };

    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      set("--hero-shift", "0px");
      set("--hero-progress", "0");
      set("--footer-progress", "1");
      set("--footer-lift", "0px");
      return unset;
    }

    const hero = document.querySelector<HTMLElement>("[data-hero]");
    const footer = document.querySelector<HTMLElement>("[data-footer-reveal]");
    // Each picture that drifts, with the frame it drifts in and where it is now.
    const pictures = Array.from(document.querySelectorAll<HTMLElement>("[data-parallax]")).map((el) => ({
      el,
      frame: el.closest<HTMLElement>("[data-parallax-frame]") ?? el.parentElement ?? el,
      shown: 0,
    }));
    // What the page is showing now, which chases the target below.
    const shown = { shift: 0, hero: 0, footer: footer ? 0 : 1 };
    let frame = 0;
    let last = 0;

    const targets = () => {
      const scrollY = window.scrollY;
      const vh = window.innerHeight;
      const footerBox = footer?.getBoundingClientRect();
      const progress = footerBox
        ? footerProgress({
            scrollY,
            viewportHeight: vh,
            footerTop: footerBox.top + scrollY,
            footerHeight: footerBox.height,
          })
        : 1;
      return {
        shift: heroShift(scrollY, vh),
        hero: heroProgress(scrollY, hero?.offsetHeight ?? vh),
        footer: progress,
        footerHeight: footerBox?.height ?? 0,
      };
    };

    const tick = (now: number) => {
      const dt = last ? Math.min(0.05, (now - last) / 1000) : 1 / 60;
      last = now;
      const target = targets();
      shown.shift = damp(shown.shift, target.shift, dt, RATE);
      shown.hero = damp(shown.hero, target.hero, dt, RATE);
      shown.footer = damp(shown.footer, target.footer, dt, RATE);

      set("--hero-shift", `${shown.shift.toFixed(1)}px`);
      set("--hero-progress", shown.hero.toFixed(3));
      set("--footer-progress", clamp01(shown.footer).toFixed(3));
      set("--footer-lift", `${footerLift(shown.footer, target.footerHeight * 0.18).toFixed(1)}px`);

      let picturesSettled = true;
      for (const picture of pictures) {
        const box = picture.frame.getBoundingClientRect();
        const want = parallaxShift({
          frameTop: box.top,
          frameHeight: box.height,
          viewportHeight: window.innerHeight,
        });
        picture.shown = damp(picture.shown, want, dt, RATE);
        picture.el.style.setProperty("--py-img", `${picture.shown.toFixed(1)}px`);
        if (Math.abs(picture.shown - want) > 0.5) picturesSettled = false;
      }

      const settled =
        picturesSettled &&
        Math.abs(shown.shift - target.shift) < SETTLED * 100 &&
        Math.abs(shown.hero - target.hero) < SETTLED &&
        Math.abs(shown.footer - target.footer) < SETTLED;
      frame = settled ? 0 : requestAnimationFrame(tick);
      if (settled) last = 0;
    };

    const start = () => {
      if (!frame) frame = requestAnimationFrame(tick);
    };

    start();
    window.addEventListener("scroll", start, { passive: true });
    window.addEventListener("resize", start);
    return () => {
      window.removeEventListener("scroll", start);
      window.removeEventListener("resize", start);
      if (frame) cancelAnimationFrame(frame);
      unset();
    };
  }, []);

  return null;
}
