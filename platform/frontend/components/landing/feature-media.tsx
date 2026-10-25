"use client";

/** The picture, video or tile in a feature's cell (see `lib/landing-features.ts` for how a
 * feature gets one). Everything is square and in the page's blue, so the six cells read as
 * a set whatever is in them.
 *
 * A video is a short silent loop: it plays only while it is on screen and never under
 * reduced motion, where the poster stands in for it. Pictures and videos are tinted to
 * the blue by default (`tone: "duotone"`); the tint is CSS over the file, so the file
 * itself stays as it was made. A picture drifts a little against the scroll (see
 * `components/landing/scroll-effects.tsx`), inside its frame. */

import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/lib/language";
import type { FeatureMedia, TilePattern } from "@/lib/landing-features";

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

/** The six generated patterns. Each is one or two gradients in two blues, so they cost no
 * bytes and stay sharp at any size. */
// Deep blue and a blue-grey for the lights, as in a two-ink print. Fixed colours, not theme
// tokens: the cells look the same in light and dark, as a printed plate would.
const BLUE = "#1f2fa0";
const LIGHT = "rgb(163 172 210 / 0.62)";
const PATTERNS: Record<TilePattern, React.CSSProperties> = {
  // A sunburst: rays from a point, with a ring around it.
  rays: {
    backgroundImage: `repeating-conic-gradient(from 0deg at 50% 52%, ${LIGHT} 0deg 2deg, transparent 2deg 7deg), radial-gradient(circle at 50% 52%, ${LIGHT} 0 7%, transparent 7.5%)`,
  },
  // Scan lines, as in a printed face.
  lines: {
    backgroundImage: `repeating-linear-gradient(0deg, ${LIGHT} 0 2px, transparent 2px 7px), linear-gradient(135deg, transparent 40%, ${LIGHT} 140%)`,
  },
  // A checkerboard bending toward a point.
  checks: {
    backgroundImage: `conic-gradient(${LIGHT} 25%, transparent 0 50%, ${LIGHT} 0 75%, transparent 0)`,
    backgroundSize: "56px 56px",
  },
  // Halftone dots.
  dots: {
    backgroundImage: `radial-gradient(${LIGHT} 22%, transparent 24%), radial-gradient(${LIGHT} 22%, transparent 24%)`,
    backgroundSize: "26px 26px",
    backgroundPosition: "0 0, 13px 13px",
  },
  // Frames inside frames.
  frames: {
    backgroundImage: `repeating-linear-gradient(90deg, ${LIGHT} 0 2px, transparent 2px 44px), repeating-linear-gradient(0deg, ${LIGHT} 0 2px, transparent 2px 44px), radial-gradient(circle at 50% 50%, ${LIGHT} 0 10%, transparent 10.5%)`,
  },
  // Waves.
  waves: {
    backgroundImage: `repeating-radial-gradient(circle at 0% 100%, transparent 0 18px, ${LIGHT} 18px 20px)`,
  },
};

/** Grain over a tile or a picture, so a flat blue has the texture of print. */
const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 160 160' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.55'/%3E%3C/svg%3E\")";

function Grain() {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 mix-blend-overlay opacity-40"
      style={{ backgroundImage: GRAIN }}
    />
  );
}

/** Tints a picture to the blue: grayscale underneath, the blue multiplied over it and the
 * lights lifted back, which is how a duotone is made. */
function Duotone({ children }: { children: React.ReactNode }) {
  return (
    <span className="relative block h-full w-full overflow-hidden bg-[#1f2fa0]">
      <span className="block h-full w-full [&>*]:contrast-125 [&>*]:grayscale [&>*]:mix-blend-luminosity">
        {children}
      </span>
      <span
        aria-hidden="true"
        className="absolute inset-0 bg-[rgb(var(--color-primary-fill))] mix-blend-multiply"
      />
      <span
        aria-hidden="true"
        className="absolute inset-0 bg-[rgb(var(--color-primary-ink)/0.35)] mix-blend-screen"
      />
      <Grain />
    </span>
  );
}

/** The pictures of a `slides` feature, taking turns. They are stacked in the one square and
 * cross-fade; the one on show carries the label. Only the current one is announced. */
/** The blue tint unless the feature asked for its pictures as they are. */
function Tint({ tone, children }: { tone?: "duotone" | "natural"; children: React.ReactNode }) {
  return tone === "natural" ? <>{children}</> : <Duotone>{children}</Duotone>;
}

function Slides({ media, playing }: { media: Extract<FeatureMedia, { kind: "slides" }>; playing: boolean }) {
  const { t } = useLanguage();
  const [index, setIndex] = useState(0);
  const [held, setHeld] = useState(false);

  useEffect(() => {
    if (!playing || held || prefersReducedMotion() || media.slides.length < 2) return;
    const id = setTimeout(() => setIndex((i) => (i + 1) % media.slides.length), media.intervalMs ?? 3400);
    return () => clearTimeout(id);
  }, [index, playing, held, media.slides.length, media.intervalMs]);

  const current = media.slides[index];
  return (
    <span
      data-slides
      className="relative block h-full w-full overflow-hidden"
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
    >
      {/* Tinted on its own so the label above it is not: a label inside the tint would be a blue
          word on blue. */}
      <Tint tone={media.tone}>
        <span className="absolute inset-0 block">
          {media.slides.map((slide, i) => (
            // Static files from /public, optimised when they were made.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={slide.src}
              src={slide.src}
              alt={t(slide.captionKey)}
              aria-hidden={i !== index}
              loading={i === 0 ? "eager" : "lazy"}
              data-slide={i === index ? "current" : undefined}
              className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-slow ease-standard ${
                i === index ? "opacity-100" : "opacity-0"
              }`}
            />
          ))}
        </span>
      </Tint>
      <span
        data-slide-label
        aria-hidden="true"
        className="eyebrow pointer-events-none absolute bottom-4 left-4 z-10 text-white/90 [text-shadow:0_1px_8px_rgb(0_0_0/0.6)]"
      >
        {t(current.titleKey)} · {t(current.captionKey)}
      </span>
    </span>
  );
}

function Video({ media, playing }: { media: Extract<FeatureMedia, { kind: "video" }>; playing: boolean }) {
  const { t } = useLanguage();
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    if (playing && !prefersReducedMotion()) {
      // A browser may refuse autoplay; the poster is then simply what shows.
      void video.play().catch(() => {});
    } else {
      video.pause();
    }
  }, [playing]);

  return (
    <video
      ref={ref}
      muted
      loop
      playsInline
      preload="metadata"
      poster={media.poster}
      aria-label={t(media.altKey)}
      className="h-full w-full object-cover"
    >
      {media.webm ? <source src={media.webm} type="video/webm" /> : null}
      <source src={media.src} type="video/mp4" />
    </video>
  );
}

export default function FeatureMediaView({
  media,
  playing = false,
}: {
  media: FeatureMedia;
  /** Whether a video should be running now; the grid passes it while the cell is on screen. */
  playing?: boolean;
}) {
  const { t } = useLanguage();

  if (media.kind === "tile") {
    return (
      <span
        aria-hidden="true"
        data-tile={media.pattern}
        className="relative block h-full w-full overflow-hidden bg-[#1f2fa0]"
      >
        <span className="absolute inset-0" style={PATTERNS[media.pattern]} />
        <Grain />
      </span>
    );
  }

  // Slides tint their own pictures (so their label is not tinted too).
  if (media.kind === "slides") return <Slides media={media} playing={playing} />;

  const natural = media.tone === "natural";
  const picture =
    media.kind === "video" ? (
      <Video media={media} playing={playing} />
    ) : (
      // A static file from /public, optimised when it was made. A single picture stays where it
      // is: only the See cell's studies, which take turns, drift as the page scrolls.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={media.src}
        alt={t(media.altKey)}
        loading="lazy"
        className={`h-full w-full ${media.fit === "contain" ? "object-contain" : "object-cover"}`}
      />
    );

  return natural ? <span className="block h-full w-full">{picture}</span> : <Duotone>{picture}</Duotone>;
}
