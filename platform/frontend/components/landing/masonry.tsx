"use client";

/** Ported from reactbits.dev/components/masonry (DavidHDev/react-bits,
 * src/content/Components/Masonry/Masonry.jsx) — animated masonry grid via
 * GSAP absolute positioning. Extended with an optional title/caption
 * overlay (reactbits' original has none) so the imaging-modality labels
 * from the gallery it replaces aren't lost. */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import { gsap } from "gsap";
import styles from "./masonry.module.css";

export interface MasonryItem {
  id: string;
  img: string;
  url?: string;
  height: number;
  title?: string;
  caption?: string;
}

type Direction = "top" | "bottom" | "left" | "right" | "center" | "random";

interface MasonryProps {
  items: MasonryItem[];
  ease?: string;
  duration?: number;
  stagger?: number;
  animateFrom?: Direction;
  scaleOnHover?: boolean;
  hoverScale?: number;
  blurToFocus?: boolean;
  colorShiftOnHover?: boolean;
}

const useMeasure = <T extends HTMLElement>() => {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setSize({ width, height });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);

  return [ref, size] as const;
};

const preloadImages = async (urls: string[]) => {
  await Promise.all(
    urls.map(
      (src) =>
        new Promise<void>((resolve) => {
          const img = new Image();
          img.src = src;
          img.onload = img.onerror = () => resolve();
        })
    )
  );
};

type GridItem = MasonryItem & { x: number; y: number; w: number; h: number };

export default function Masonry({
  items,
  ease = "power3.out",
  duration = 0.6,
  stagger = 0.05,
  animateFrom = "bottom",
  scaleOnHover = true,
  hoverScale = 0.95,
  blurToFocus = true,
  colorShiftOnHover = false,
  onLayout,
}: MasonryProps & { onLayout?: (height: number) => void }) {
  // Widest match wins, read top-down. One column below 400px — with absolute
  // positioning, two columns on a narrow phone means ~150px-wide cards.
  const xl = useMediaQuery("(min-width:1500px)");
  const lg = useMediaQuery("(min-width:1000px)");
  const md = useMediaQuery("(min-width:600px)");
  const sm = useMediaQuery("(min-width:400px)");
  const columns = xl ? 5 : lg ? 4 : md ? 3 : sm ? 2 : 1;

  // The entrance choreography is decoration; honouring the OS setting costs one
  // branch. `globals.css` already does the same for smooth scrolling.
  const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  const [containerRef, { width }] = useMeasure<HTMLDivElement>();
  const [imagesReady, setImagesReady] = useState(false);

  const getInitialPosition = (item: GridItem) => {
    const containerRect = containerRef.current?.getBoundingClientRect();
    if (!containerRect) return { x: item.x, y: item.y };

    let direction = animateFrom;
    if (animateFrom === "random") {
      const directions: Direction[] = ["top", "bottom", "left", "right"];
      direction = directions[Math.floor(Math.random() * directions.length)];
    }

    switch (direction) {
      case "top":
        return { x: item.x, y: -200 };
      case "bottom":
        return { x: item.x, y: window.innerHeight + 200 };
      case "left":
        return { x: -200, y: item.y };
      case "right":
        return { x: window.innerWidth + 200, y: item.y };
      case "center":
        return {
          x: containerRect.width / 2 - item.w / 2,
          y: containerRect.height / 2 - item.h / 2,
        };
      default:
        return { x: item.x, y: item.y + 100 };
    }
  };

  useEffect(() => {
    preloadImages(items.map((i) => i.img)).then(() => setImagesReady(true));
  }, [items]);

  const grid = useMemo<GridItem[]>(() => {
    if (!width) return [];

    const colHeights = new Array(columns).fill(0);
    const columnWidth = width / columns;

    return items.map((child) => {
      const col = colHeights.indexOf(Math.min(...colHeights));
      const x = columnWidth * col;
      const height = child.height / 2;
      const y = colHeights[col];

      colHeights[col] += height;

      return { ...child, x, y, w: columnWidth, h: height };
    });
  }, [columns, items, width]);

  useEffect(() => {
    if (!grid.length || !onLayout) return;
    const tallest = Math.max(...grid.map((item) => item.y + item.h));
    onLayout(tallest);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grid]);

  const hasMounted = useRef(false);

  useLayoutEffect(() => {
    if (!imagesReady) return;

    grid.forEach((item, index) => {
      const selector = `[data-key="${item.id}"]`;
      const animationProps = { x: item.x, y: item.y, width: item.w, height: item.h };

      if (reduceMotion) {
        // Land in the final layout with no fly-in and no stagger. `gsap.set`
        // rather than a zero duration so nothing is ever painted mid-flight.
        gsap.set(selector, { opacity: 1, filter: "none", ...animationProps });
      } else if (!hasMounted.current) {
        const initialPos = getInitialPosition(item);
        const initialState = {
          opacity: 0,
          x: initialPos.x,
          y: initialPos.y,
          width: item.w,
          height: item.h,
          ...(blurToFocus && { filter: "blur(10px)" }),
        };

        gsap.fromTo(selector, initialState, {
          opacity: 1,
          ...animationProps,
          ...(blurToFocus && { filter: "blur(0px)" }),
          duration: 0.8,
          ease: "power3.out",
          delay: index * stagger,
        });
      } else {
        gsap.to(selector, {
          ...animationProps,
          duration,
          ease,
          overwrite: "auto",
        });
      }
    });

    hasMounted.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grid, imagesReady, stagger, animateFrom, blurToFocus, duration, ease, reduceMotion]);

  const handleMouseEnter = (e: React.MouseEvent<HTMLDivElement>, item: GridItem) => {
    const selector = `[data-key="${item.id}"]`;
    if (scaleOnHover) {
      gsap.to(selector, { scale: hoverScale, duration: 0.3, ease: "power2.out" });
    }
    if (colorShiftOnHover) {
      const overlay = e.currentTarget.querySelector<HTMLElement>(".color-overlay");
      if (overlay) gsap.to(overlay, { opacity: 0.3, duration: 0.3 });
    }
  };

  const handleMouseLeave = (e: React.MouseEvent<HTMLDivElement>, item: GridItem) => {
    const selector = `[data-key="${item.id}"]`;
    if (scaleOnHover) {
      gsap.to(selector, { scale: 1, duration: 0.3, ease: "power2.out" });
    }
    if (colorShiftOnHover) {
      const overlay = e.currentTarget.querySelector<HTMLElement>(".color-overlay");
      if (overlay) gsap.to(overlay, { opacity: 0, duration: 0.3 });
    }
  };

  return (
    <div ref={containerRef} className={styles.list}>
      {grid.map((item) => (
        <div
          key={item.id}
          data-key={item.id}
          className={styles.itemWrapper}
          onClick={() => item.url && window.open(item.url, "_blank", "noopener")}
          onMouseEnter={(e) => handleMouseEnter(e, item)}
          onMouseLeave={(e) => handleMouseLeave(e, item)}
        >
          <div
            className={styles.itemImg}
            style={{ backgroundImage: `url(${item.img})` }}
            role="img"
            aria-label={item.title ?? item.caption ?? "Medical imaging analysis example"}
          >
            {colorShiftOnHover && (
              <div
                className="color-overlay"
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: "100%",
                  background: "linear-gradient(45deg, rgba(255,0,150,0.5), rgba(0,150,255,0.5))",
                  opacity: 0,
                  pointerEvents: "none",
                  borderRadius: "8px",
                }}
              />
            )}
            {(item.title || item.caption) && (
              <div className={styles.caption}>
                {item.title && <p className={styles.captionTitle}>{item.title}</p>}
                {item.caption && <p className={styles.captionText}>{item.caption}</p>}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
