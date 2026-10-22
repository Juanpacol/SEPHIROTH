"use client";

/** The picture, video or tile in a feature's media panel (see `lib/landing-features.ts`
 * for how a feature gets one).
 *
 * A video is a short silent loop: it plays only while `playing` is true (its feature is
 * the one in view) and never under reduced motion, where the poster stands in for it.
 * `still` shows the poster instead of the video, for the small-screen copy of a panel. */

import { useEffect, useRef } from "react";
import { useLanguage } from "@/lib/language";
import type { FeatureMedia } from "@/lib/landing-features";

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
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
      className="media-edge h-full w-full object-cover"
    >
      {media.webm ? <source src={media.webm} type="video/webm" /> : null}
      <source src={media.src} type="video/mp4" />
    </video>
  );
}

/** The tile a feature has until it has media: its number and verb, large, on a quiet
 * gradient. Decorative, so hidden from assistive technology. */
function Tile({ index, verb }: { index: number; verb: string }) {
  return (
    <div
      aria-hidden="true"
      className="relative flex h-full w-full flex-col justify-between overflow-hidden bg-surface p-6 sm:p-8"
      style={{
        backgroundImage:
          "radial-gradient(70% 60% at 85% 10%, rgb(var(--color-primary-ink) / 0.28), transparent 70%), radial-gradient(60% 60% at 0% 100%, rgb(var(--color-primary-soft) / 0.9), transparent 70%)",
      }}
    >
      <span className="eyebrow text-primary-ink">{verb}</span>
      <span className="font-display text-[clamp(7rem,22vw,14rem)] font-semibold leading-[0.8] text-ink/15">
        {String(index + 1).padStart(2, "0")}
      </span>
    </div>
  );
}

export default function FeatureMediaView({
  media,
  index,
  verb,
  playing = false,
  still = false,
}: {
  media: FeatureMedia;
  index: number;
  verb: string;
  playing?: boolean;
  still?: boolean;
}) {
  const { t } = useLanguage();

  if (media.kind === "video") {
    return still ? (
      // The poster is a plain picture: no motion to offer or withhold.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={media.poster}
        alt={t(media.altKey)}
        loading="lazy"
        className="media-edge h-full w-full object-cover"
      />
    ) : (
      <Video media={media} playing={playing} />
    );
  }
  if (media.kind === "image") {
    return (
      // A static file from /public, optimised when it was made.
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={media.src}
        alt={t(media.altKey)}
        loading="lazy"
        className="media-edge h-full w-full object-cover"
      />
    );
  }
  return <Tile index={index} verb={verb} />;
}
