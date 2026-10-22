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
  /** A short, silent loop. `poster` is what shows before it loads, and the whole time under
   * reduced motion. Keep it under 3 MB; mp4 (H.264) for Safari plus webm if you can. */
  | { kind: "video"; src: string; poster: string; altKey: string; webm?: string; tone?: FeatureTone };

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
    media: { kind: "tile", pattern: "rays" },
  },
  {
    // `verification/citation_guard.py` and the evidence agent: guidelines and PubMed only.
    id: "cite",
    verbKey: "marketing.features.cite.verb",
    titleKey: "marketing.features.cite.title",
    bodyKey: "marketing.features.cite.body",
    media: { kind: "tile", pattern: "lines" },
  },
  {
    // `verification/` (five claim states) and `safety/abstention.py`.
    id: "verify",
    verbKey: "marketing.features.verify.verb",
    titleKey: "marketing.features.verify.title",
    bodyKey: "marketing.features.verify.body",
    media: { kind: "tile", pattern: "checks" },
  },
  {
    // `intelligence/mcp/vision_server.py`: a description of what is visible, not a diagnosis.
    id: "see",
    verbKey: "marketing.features.see.verb",
    titleKey: "marketing.features.see.title",
    bodyKey: "marketing.features.see.body",
    media: { kind: "image", src: "/landing/analysis/xray.webp", altKey: "marketing.features.see.alt" },
  },
  {
    // `clinical/results.py` and the results inbox: reference ranges, critical values, review.
    id: "follow",
    verbKey: "marketing.features.follow.verb",
    titleKey: "marketing.features.follow.title",
    bodyKey: "marketing.features.follow.body",
    media: { kind: "tile", pattern: "dots" },
  },
  {
    // `api/patient_labs.py`: a patient sees a result only after a clinician has communicated it.
    id: "share",
    verbKey: "marketing.features.share.verb",
    titleKey: "marketing.features.share.title",
    bodyKey: "marketing.features.share.body",
    media: { kind: "tile", pattern: "frames" },
  },
];
