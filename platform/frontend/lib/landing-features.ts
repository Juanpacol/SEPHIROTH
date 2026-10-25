/** The landing page's feature grid: what SEPHIROTH does, six cells in the manner of the
 * Hermes Agent site: a numbered label, a title, a paragraph and a square picture under
 * each. Every claim here is something the product does today; the comment on each names
 * where.
 *
 * To put a picture or a video in a cell, add the file under `public/landing/features/`
 * and fill in that feature's `media` below (see the README in that folder). A feature
 * with no media shows a generated tile (a pattern of its own in the page's blue), so the
 * grid is finished either way. */
export type FeatureTone = "duotone" | "natural";

export type FeatureMedia =
  /** A generated blue pattern. `pattern` picks which of the six. */
  | { kind: "tile"; pattern: TilePattern }
  /** `tone: "duotone"` (the default) tints it to the page's blue, like the rest of the
   * grid; `"natural"` leaves it as it is. */
  | { kind: "image"; src: string; altKey: string; tone?: FeatureTone }
  /** Several pictures that take turns in the same square, cross-fading. Only while the cell is on
   * screen, and never under reduced motion, where the first one stays. Each carries a short
   * description (`altKey`) and a label shown on it (`titleKey`, `captionKey`). */
  | { kind: "slides"; slides: FeatureSlide[]; intervalMs?: number; tone?: FeatureTone }
  /** A short, silent loop. `poster` is what shows before it loads, and the whole time under
   * reduced motion. Keep it under 3 MB; mp4 (H.264) for Safari plus webm if you can. */
  | { kind: "video"; src: string; poster: string; altKey: string; webm?: string; tone?: FeatureTone };

export interface FeatureSlide {
  src: string;
  titleKey: string;
  captionKey: string;
}

export type TilePattern = "rays" | "lines" | "checks" | "dots" | "frames" | "waves";

export interface LandingFeature {
  id: string;
  verbKey: string;
  titleKey: string;
  bodyKey: string;
  media: FeatureMedia;
}

export const LANDING_FEATURES: LandingFeature[] = [
  {
    // `runtime/intent_router.py`: every question goes to exactly one specialist.
    id: "ask",
    verbKey: "marketing.features.ask.verb",
    titleKey: "marketing.features.ask.title",
    bodyKey: "marketing.features.ask.body",
    media: { kind: "image", src: "/landing/features/ask-spine.webp", altKey: "marketing.features.ask.alt" },
  },
  {
    // `verification/citation_guard.py` and the evidence agent: guidelines and PubMed only.
    id: "cite",
    verbKey: "marketing.features.cite.verb",
    titleKey: "marketing.features.cite.title",
    bodyKey: "marketing.features.cite.body",
    media: {
      kind: "image",
      src: "/landing/features/cite-annotated-figure.webp",
      altKey: "marketing.features.cite.alt",
    },
  },
  {
    // `verification/` (five claim states) and `safety/abstention.py`.
    id: "verify",
    verbKey: "marketing.features.verify.verb",
    titleKey: "marketing.features.verify.title",
    bodyKey: "marketing.features.verify.body",
    media: {
      kind: "image",
      src: "/landing/features/verify-eye.webp",
      altKey: "marketing.features.verify.alt",
    },
  },
  {
    // `intelligence/mcp/vision_server.py`: a description of what is visible, not a diagnosis.
    id: "see",
    verbKey: "marketing.features.see.verb",
    titleKey: "marketing.features.see.title",
    bodyKey: "marketing.features.see.body",
    // One example study, with its label: the picture stays where it is.
    media: {
      kind: "slides",
      slides: [
        {
          src: "/landing/analysis/pathology.webp",
          titleKey: "marketing.analysisGallery.pathology.title",
          captionKey: "marketing.analysisGallery.pathology.caption",
        },
      ],
    },
  },
  {
    // `clinical/results.py` and the results inbox: reference ranges, critical values, review.
    id: "follow",
    verbKey: "marketing.features.follow.verb",
    titleKey: "marketing.features.follow.title",
    bodyKey: "marketing.features.follow.body",
    media: {
      kind: "image",
      src: "/landing/features/follow-waveform.webp",
      altKey: "marketing.features.follow.alt",
    },
  },
  {
    // `api/patient_labs.py`: a patient sees a result only after a clinician has communicated it.
    id: "share",
    verbKey: "marketing.features.share.verb",
    titleKey: "marketing.features.share.title",
    bodyKey: "marketing.features.share.body",
    media: {
      kind: "image",
      src: "/landing/features/share-hands.webp",
      altKey: "marketing.features.share.alt",
    },
  },
];
